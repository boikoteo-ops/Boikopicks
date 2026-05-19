"""
listin_guia.py — Quinta fuente de picks: Guía Deportiva del Listín Diario.

Estrategia v5 (CONFIRMADA con JSON real del visor 2026-05-19):
  El endpoint https://www.yumpu.com/es/document/json/{numericId} devuelve:
    {
      "document": {
        "base_path": "https://documents.yumpu.com/000/071/115/786/<hash>/",
        "pages": [
          { "nr": 1, "images": {"thumb": "...", "small": "...",
                                "medium": "...", "large": "...", "zoom": "..."} },
          ...
        ],
        ...
      },
      ...
    }
  Las imágenes son rutas relativas. URL completa = base_path + images[size].

Flujo:
  1. Buscar el artículo de la Guía Deportiva del día en listindiario.com
  2. Extraer hash de Yumpu del HTML del artículo
  3. Fetch al visor → extraer numericId
  4. Fetch al endpoint JSON → obtener pages + base_path
  5. Bajar imágenes (preferir 'large')
  6. OCR español
  7. Parsear picks
"""
from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

LISTIN_BASE = "https://listindiario.com"
GUIA_INDEX = f"{LISTIN_BASE}/el-deporte/guia-deportiva"
YUMPU_EMBED = "https://www.yumpu.com/es/embed/view/{hash_id}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
MAX_PAGES_HARD_CAP = 12

# Orden de preferencia: la mejor resolución legible para OCR es "large".
# "zoom" suele ser el más grande pero a veces está vacío. Fallback en cascada.
IMAGE_SIZE_PREFERENCE = ["zoom", "large", "medium", "small", "thumb"]

NUMERIC_ID_PATTERNS = [
    re.compile(r'"jsonUrl"\s*:\s*"[^"]*?/document/json/(\d+)'),
    re.compile(r'/document/view/(\d+)/'),
    re.compile(r'/document/readers/(\d+)'),
]


@dataclass
class GuiaPick:
    sport: str
    matchup: str
    pick: str
    raw_line: str


@dataclass
class GuiaResult:
    fecha: date
    article_url: str = ""
    yumpu_hash: Optional[str] = None
    yumpu_numeric_id: Optional[str] = None
    pages_downloaded: int = 0
    picks: list[GuiaPick] = field(default_factory=list)
    ocr_text: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source": "listin_guia",
            "fecha": self.fecha.isoformat(),
            "url": self.article_url,
            "yumpu_hash": self.yumpu_hash,
            "yumpu_numeric_id": self.yumpu_numeric_id,
            "pages": self.pages_downloaded,
            "picks_mlb": [{"matchup": p.matchup, "pick": p.pick}
                          for p in self.picks if p.sport == "MLB"],
            "picks_nba": [{"matchup": p.matchup, "pick": p.pick}
                          for p in self.picks if p.sport == "NBA"],
            "error": self.error,
        }


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,*/*;q=0.8",
        "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
    })
    return s


# ---------------------------------------------------------------------------
# 1. Artículo del día
# ---------------------------------------------------------------------------

def find_article_url(target_date: date, session: requests.Session) -> Optional[str]:
    date_token = target_date.strftime("%Y%m%d")
    date_token_dashed = target_date.strftime("%d-%m-%Y")

    for page in (1, 2):
        url = GUIA_INDEX if page == 1 else f"{GUIA_INDEX}/{page}"
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
        except requests.RequestException as e:
            log.warning("No se pudo cargar índice página %d: %s", page, e)
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/guia-deportiva/" in href and (date_token in href or date_token_dashed in href):
                full = href if href.startswith("http") else LISTIN_BASE + href
                log.info("Artículo encontrado: %s", full)
                return full

    log.warning("No se encontró artículo para %s", target_date)
    return None


# ---------------------------------------------------------------------------
# 2. Hash Yumpu del artículo del Listín
# ---------------------------------------------------------------------------

YUMPU_HASH_PATTERNS = [
    re.compile(r"yumpu\.com/[a-z]{2}/embed/view/([A-Za-z0-9]+)"),
    re.compile(r"yumpu\.com/[a-z]{2}/document/view/\d+/([A-Za-z0-9]+)"),
]


def extract_yumpu_hash(article_html: str) -> Optional[str]:
    for pattern in YUMPU_HASH_PATTERNS:
        m = pattern.search(article_html)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 3. Numeric ID del visor
# ---------------------------------------------------------------------------

def extract_numeric_id(viewer_html: str) -> Optional[str]:
    for pattern in NUMERIC_ID_PATTERNS:
        m = pattern.search(viewer_html)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 4. JSON oficial → URLs absolutas de imágenes
# ---------------------------------------------------------------------------

def fetch_document_json(numeric_id: str, session: requests.Session) -> Optional[dict]:
    url = f"https://www.yumpu.com/es/document/json/{numeric_id}"
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT,
                        headers={"Accept": "application/json, text/plain, */*"})
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.error("Error obteniendo JSON del documento: %s", e)
        return None


def build_page_image_urls(doc_json: dict) -> list[tuple[int, str]]:
    """
    De `document.pages[].images` + `document.base_path` arma URLs absolutas.
    Devuelve [(page_num, url_mejor_resolucion), ...] ordenado por página.
    """
    document = doc_json.get("document")
    if not isinstance(document, dict):
        log.warning("JSON no contiene 'document' como dict")
        return []

    base_path = document.get("base_path", "")
    if not base_path:
        log.warning("'document.base_path' vacío")
        return []
    if not base_path.endswith("/"):
        base_path += "/"

    pages = document.get("pages")
    if not isinstance(pages, list):
        log.warning("'document.pages' no es lista")
        return []

    result: list[tuple[int, str]] = []
    for page_obj in pages[:MAX_PAGES_HARD_CAP]:
        if not isinstance(page_obj, dict):
            continue
        page_nr = page_obj.get("nr")
        if not isinstance(page_nr, int):
            continue

        images = page_obj.get("images")
        if not isinstance(images, dict):
            log.debug("Página %d sin 'images'", page_nr)
            continue

        # Tomar la mejor resolución disponible (no vacía)
        chosen_path = None
        chosen_size = None
        for size in IMAGE_SIZE_PREFERENCE:
            path = images.get(size)
            if isinstance(path, str) and path.strip():
                chosen_path = path.strip()
                chosen_size = size
                break

        if chosen_path is None:
            log.debug("Página %d sin imagen utilizable", page_nr)
            continue

        # Path puede ser absoluto o relativo
        if chosen_path.startswith("http://") or chosen_path.startswith("https://"):
            full_url = chosen_path
        else:
            full_url = base_path + chosen_path.lstrip("/")

        log.info("Página %d: tamaño=%s url=%s", page_nr, chosen_size, full_url[:120])
        result.append((page_nr, full_url))

    log.info("Total URLs construidas: %d", len(result))
    return result


# ---------------------------------------------------------------------------
# 5. Bajar imágenes
# ---------------------------------------------------------------------------

def download_images(image_specs: list[tuple[int, str]], session: requests.Session,
                    dest_dir: Path) -> list[Path]:
    saved: list[Path] = []
    for page_num, url in image_specs:
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            ctype = r.headers.get("Content-Type", "")
            if r.status_code != 200 or not ctype.startswith("image/"):
                log.warning("Página %d: status=%d ctype=%s url=%s",
                            page_num, r.status_code, ctype, url[:100])
                continue
            ext = ".jpg" if ("jpeg" in ctype or "jpg" in ctype) else ".png"
            dest = dest_dir / f"page_{page_num:02d}{ext}"
            dest.write_bytes(r.content)
            log.info("Página %d descargada: %d bytes -> %s", page_num, len(r.content), dest.name)
            saved.append(dest)
        except requests.RequestException as e:
            log.warning("Error de red página %d: %s", page_num, e)
    log.info("Total páginas descargadas: %d", len(saved))
    return saved


# ---------------------------------------------------------------------------
# 6. OCR
# ---------------------------------------------------------------------------

def ocr_images(image_paths: list[Path]) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Faltan dependencias: pip install pytesseract Pillow") from e

    pieces = []
    for i, path in enumerate(image_paths, 1):
        try:
            with Image.open(path) as img:
                text = pytesseract.image_to_string(img, lang="spa")
            pieces.append(f"--- PAGE {i} ({path.name}) ---\n{text}")
            log.info("Página %d OCR: %d chars", i, len(text))
        except Exception as e:
            log.warning("OCR falló en página %d (%s): %s", i, path.name, e)
            pieces.append(f"--- PAGE {i} ({path.name}) — OCR ERROR: {e} ---")
    return "\n\n".join(pieces)


# ---------------------------------------------------------------------------
# 7. Parsear picks
# ---------------------------------------------------------------------------

MLB_TEAMS = {
    "Yankees", "Red Sox", "Blue Jays", "Rays", "Orioles",
    "Guardians", "Tigers", "Twins", "Royals", "White Sox",
    "Astros", "Rangers", "Mariners", "Athletics", "Angels",
    "Braves", "Mets", "Phillies", "Marlins", "Nationals",
    "Cubs", "Reds", "Brewers", "Pirates", "Cardinals",
    "Dodgers", "Padres", "Giants", "Rockies", "Diamondbacks",
}
NBA_TEAMS = {
    "Celtics", "Nets", "Knicks", "76ers", "Raptors",
    "Bulls", "Cavaliers", "Pistons", "Pacers", "Bucks",
    "Hawks", "Hornets", "Heat", "Magic", "Wizards",
    "Nuggets", "Timberwolves", "Thunder", "Trail Blazers", "Jazz",
    "Warriors", "Clippers", "Lakers", "Suns", "Kings",
    "Mavericks", "Rockets", "Grizzlies", "Pelicans", "Spurs",
}


def _classify_line(line: str) -> Optional[str]:
    mlb_hits = sum(1 for t in MLB_TEAMS if t in line)
    nba_hits = sum(1 for t in NBA_TEAMS if t in line)
    if mlb_hits >= 1 and mlb_hits >= nba_hits:
        return "MLB"
    if nba_hits >= 1:
        return "NBA"
    return None


def parse_picks(ocr_text: str) -> list[GuiaPick]:
    picks: list[GuiaPick] = []
    for raw in ocr_text.splitlines():
        line = raw.strip()
        if len(line) < 10 or len(line) > 200 or line.startswith("--- PAGE"):
            continue
        sport = _classify_line(line)
        if sport is None:
            continue
        teams = MLB_TEAMS if sport == "MLB" else NBA_TEAMS
        found = [t for t in teams if t in line]
        matchup = " vs ".join(found[:2]) if len(found) >= 2 else (found[0] if found else "?")
        picks.append(GuiaPick(sport=sport, matchup=matchup, pick=line, raw_line=raw))

    log.info("Picks extraídos: %d MLB, %d NBA",
             sum(1 for p in picks if p.sport == "MLB"),
             sum(1 for p in picks if p.sport == "NBA"))
    return picks


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def fetch_guia(target_date: Optional[date] = None,
               work_dir: Optional[Path] = None) -> GuiaResult:
    if target_date is None:
        target_date = datetime.now().date()
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="listin_guia_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    result = GuiaResult(fecha=target_date)
    session = _session()

    # 1. Artículo
    article_url = find_article_url(target_date, session)
    if not article_url:
        result.error = "no_article_found"
        return result
    result.article_url = article_url

    # 2. Hash
    try:
        r = session.get(article_url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        result.error = f"article_fetch_failed: {e}"
        return result

    yumpu_hash = extract_yumpu_hash(r.text)
    if not yumpu_hash:
        result.error = "no_yumpu_hash_in_article"
        return result
    result.yumpu_hash = yumpu_hash
    log.info("Yumpu hash: %s", yumpu_hash)

    # 3. Numeric ID
    viewer_url = YUMPU_EMBED.format(hash_id=yumpu_hash)
    try:
        rv = session.get(viewer_url, timeout=REQUEST_TIMEOUT)
        rv.raise_for_status()
    except requests.RequestException as e:
        result.error = f"viewer_fetch_failed: {e}"
        return result

    numeric_id = extract_numeric_id(rv.text)
    if not numeric_id:
        result.error = "no_numeric_id_in_viewer"
        return result
    result.yumpu_numeric_id = numeric_id
    log.info("Numeric ID: %s", numeric_id)

    # 4. JSON
    doc_json = fetch_document_json(numeric_id, session)
    if doc_json is None:
        result.error = "json_fetch_failed"
        return result

    # Guardar JSON crudo (siempre, útil para auditar)
    json_debug = work_dir / f"doc_json_{target_date.isoformat()}_{numeric_id}.json"
    json_debug.write_text(json.dumps(doc_json, indent=2, ensure_ascii=False), encoding="utf-8")

    image_specs = build_page_image_urls(doc_json)
    if not image_specs:
        result.error = "no_image_urls_in_json"
        return result

    # 5. Bajar imágenes
    pages_dir = work_dir / f"pages_{target_date.isoformat()}_{numeric_id}"
    pages_dir.mkdir(exist_ok=True)
    page_images = download_images(image_specs, session, pages_dir)
    result.pages_downloaded = len(page_images)

    if not page_images:
        result.error = "no_pages_downloaded"
        return result

    # 6. OCR
    try:
        ocr_text = ocr_images(page_images)
    except Exception as e:
        log.exception("OCR falló")
        result.error = f"ocr_failed: {e}"
        return result
    result.ocr_text = ocr_text

    # 7. Picks
    result.picks = parse_picks(ocr_text)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    res = fetch_guia()
    print(f"\nFecha:        {res.fecha}")
    print(f"URL:          {res.article_url}")
    print(f"Yumpu hash:   {res.yumpu_hash}")
    print(f"Numeric ID:   {res.yumpu_numeric_id}")
    print(f"Páginas:      {res.pages_downloaded}")
    print(f"Error:        {res.error}")
    print(f"MLB:          {sum(1 for p in res.picks if p.sport == 'MLB')}")
    print(f"NBA:          {sum(1 for p in res.picks if p.sport == 'NBA')}")
