"""
listin_guia.py — Quinta fuente de picks: Guía Deportiva del Listín Diario.

Estrategia v3 (post-test 2026-05-19, segundo intento):
  El visor embebido de Yumpu (/embed/view/{hash}) contiene en su HTML las
  URLs reales de las imágenes de páginas (img.yumpu.com/...). En vez de
  adivinar el patrón, las extraemos directamente del HTML del visor.

  Yumpu sirve esas imágenes públicamente sin auth.

Flujo:
  1. Buscar el artículo de la Guía Deportiva del día en listindiario.com
  2. Extraer el hash de Yumpu (ej. rPaCwL2b1VHg3Wt0) del HTML del artículo
  3. Fetch al visor https://www.yumpu.com/es/embed/view/{hash}
  4. Extraer todas las URLs img.yumpu.com/{numId}/{page}/.../{slug}.jpg
  5. Bajar las imágenes (preferir resolución más alta disponible)
  6. OCR de cada imagen con Tesseract español
  7. Parsear el texto para extraer picks de MLB y NBA

Dependencias del SO:
    tesseract-ocr, tesseract-ocr-spa
Dependencias Python:
    requests, beautifulsoup4, pytesseract, Pillow
"""
from __future__ import annotations

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
MAX_PAGES_HARD_CAP = 12  # Tope de seguridad

# Patrón confirmado por docs públicas de Yumpu:
#   https://img.yumpu.com/{numericId}/{pageNum}/{WxH}/{slug}.jpg
IMG_URL_RE = re.compile(
    r"https?://img\.yumpu\.com/(\d+)/(\d+)/(\d+x\d+)/([^\"'\s<>]+\.(?:jpg|jpeg|png))",
    re.IGNORECASE,
)


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
            "picks_mlb": [
                {"matchup": p.matchup, "pick": p.pick}
                for p in self.picks if p.sport == "MLB"
            ],
            "picks_nba": [
                {"matchup": p.matchup, "pick": p.pick}
                for p in self.picks if p.sport == "NBA"
            ],
            "error": self.error,
        }


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
    })
    return s


# ---------------------------------------------------------------------------
# Paso 1: Encontrar artículo del día
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
# Paso 2: Extraer hash de Yumpu del HTML del artículo
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
# Paso 3-4: Obtener URLs de imágenes desde el HTML del visor
# ---------------------------------------------------------------------------

def extract_image_urls(viewer_html: str) -> tuple[Optional[str], list[tuple[int, str]]]:
    """
    Devuelve (numeric_id, [(page_num, url_mayor_resolucion), ...]) ordenado.
    Si una página aparece con varias resoluciones, conservamos la mayor (área).
    """
    matches = IMG_URL_RE.findall(viewer_html)
    if not matches:
        return None, []

    # matches = [(num_id, page, "WxH", filename_part), ...]
    # Agrupar por página, quedarnos con la mayor resolución
    best_per_page: dict[int, tuple[int, str]] = {}  # page -> (area, url)
    numeric_id = None

    for num_id, page_str, dims, filename in matches:
        if numeric_id is None:
            numeric_id = num_id
        elif num_id != numeric_id:
            # Documento distinto en el HTML, ignoramos
            continue

        try:
            page = int(page_str)
            w, h = (int(x) for x in dims.lower().split("x"))
            area = w * h
        except ValueError:
            continue

        url = f"https://img.yumpu.com/{num_id}/{page}/{dims}/{filename}"
        prev = best_per_page.get(page)
        if prev is None or area > prev[0]:
            best_per_page[page] = (area, url)

    sorted_pages = sorted(best_per_page.items())[:MAX_PAGES_HARD_CAP]
    urls = [(page, area_url[1]) for page, area_url in sorted_pages]
    log.info("URLs de imágenes extraídas: %d páginas (numeric_id=%s)", len(urls), numeric_id)
    return numeric_id, urls


def download_images(image_specs: list[tuple[int, str]], session: requests.Session,
                    dest_dir: Path) -> list[Path]:
    saved: list[Path] = []
    for page_num, url in image_specs:
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            ctype = r.headers.get("Content-Type", "")
            if r.status_code != 200 or not ctype.startswith("image/"):
                log.warning("Página %d: status=%d ctype=%s url=%s",
                            page_num, r.status_code, ctype, url)
                continue
            ext = ".jpg" if "jpeg" in ctype or "jpg" in ctype else ".png"
            dest = dest_dir / f"page_{page_num:02d}{ext}"
            dest.write_bytes(r.content)
            log.debug("Página %d: %d bytes -> %s", page_num, len(r.content), dest.name)
            saved.append(dest)
        except requests.RequestException as e:
            log.warning("Error de red página %d: %s", page_num, e)

    log.info("Total páginas descargadas: %d", len(saved))
    return saved


# ---------------------------------------------------------------------------
# Paso 5: OCR
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
            log.debug("Página %d: %d chars OCR", i, len(text))
        except Exception as e:
            log.warning("OCR falló en página %d (%s): %s", i, path.name, e)
            pieces.append(f"--- PAGE {i} ({path.name}) — OCR ERROR: {e} ---")
    return "\n\n".join(pieces)


# ---------------------------------------------------------------------------
# Paso 6: Parsear picks
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

    # 1. Artículo del día
    article_url = find_article_url(target_date, session)
    if not article_url:
        result.error = "no_article_found"
        return result
    result.article_url = article_url

    # 2. Hash de Yumpu
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

    # 3. Fetch del visor para obtener URLs de imágenes
    viewer_url = YUMPU_EMBED.format(hash_id=yumpu_hash)
    try:
        rv = session.get(viewer_url, timeout=REQUEST_TIMEOUT)
        rv.raise_for_status()
    except requests.RequestException as e:
        result.error = f"viewer_fetch_failed: {e}"
        return result

    numeric_id, image_specs = extract_image_urls(rv.text)
    result.yumpu_numeric_id = numeric_id

    if not image_specs:
        result.error = "no_image_urls_in_viewer"
        # Guardamos el HTML del visor para debug
        debug_path = work_dir / f"viewer_debug_{target_date.isoformat()}.html"
        debug_path.write_text(rv.text, encoding="utf-8", errors="replace")
        log.warning("Sin URLs de imágenes. HTML del visor guardado en %s", debug_path)
        return result

    # 4. Bajar imágenes
    pages_dir = work_dir / f"pages_{target_date.isoformat()}_{numeric_id}"
    pages_dir.mkdir(exist_ok=True)
    page_images = download_images(image_specs, session, pages_dir)
    result.pages_downloaded = len(page_images)

    if not page_images:
        result.error = "no_pages_downloaded"
        return result

    # 5. OCR
    try:
        ocr_text = ocr_images(page_images)
    except Exception as e:
        log.exception("OCR falló")
        result.error = f"ocr_failed: {e}"
        return result
    result.ocr_text = ocr_text

    # 6. Picks
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
