"""
listin_guia.py — Quinta fuente de picks: Guía Deportiva del Listín Diario.

Estrategia v2 (post-test 2026-05-19):
  Yumpu protege el PDF directo (404 en /document/pdf/{id}.pdf), pero expone
  las IMÁGENES de cada página vía CDN público. Bajamos cada página como JPG
  y le hacemos OCR directo, saltando pdf2image.

Flujo:
  1. Buscar el artículo de la Guía Deportiva del día en listindiario.com
  2. Extraer el ID del documento de Yumpu embebido
  3. Bajar imágenes de páginas (page-1.jpg, page-2.jpg, ...) hasta 404
  4. OCR de cada imagen con Tesseract (español)
  5. Parsear el texto para extraer picks de MLB y NBA

Dependencias del SO (Ubuntu en GitHub Actions):
    sudo apt-get install -y tesseract-ocr tesseract-ocr-spa

Dependencias Python:
    requests
    beautifulsoup4
    pytesseract
    Pillow
"""
from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

LISTIN_BASE = "https://listindiario.com"
GUIA_INDEX = f"{LISTIN_BASE}/el-deporte/guia-deportiva"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

# Yumpu CDN — patrones observados en el visor. Probamos varios formatos
# porque Yumpu sirve varias resoluciones; preferimos la más grande.
YUMPU_IMG_TEMPLATES = [
    "https://img.yumpu.com/{doc_id}/{page}/1500x2120/page-{page}.jpg",
    "https://img.yumpu.com/{doc_id}/{page}/1080x1527/page-{page}.jpg",
    "https://img.yumpu.com/{doc_id}/{page}/720x1018/page-{page}.jpg",
]
MAX_PAGES = 8       # Tope de seguridad por documento
MAX_404_RETRY = 2   # Si el primer template da 404, probar siguientes


@dataclass
class GuiaPick:
    sport: str            # "MLB" | "NBA"
    matchup: str
    pick: str
    raw_line: str


@dataclass
class GuiaResult:
    fecha: date
    article_url: str
    yumpu_id: Optional[str]
    pages_downloaded: int = 0
    picks: list[GuiaPick] = field(default_factory=list)
    ocr_text: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source": "listin_guia",
            "fecha": self.fecha.isoformat(),
            "url": self.article_url,
            "yumpu_id": self.yumpu_id,
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
# Paso 1: Encontrar el artículo del día
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

    log.warning("No se encontró artículo de la Guía para %s", target_date)
    return None


# ---------------------------------------------------------------------------
# Paso 2: Extraer ID de Yumpu del HTML del artículo
# ---------------------------------------------------------------------------

YUMPU_PATTERNS = [
    re.compile(r"yumpu\.com/[a-z]{2}/embed/view/([A-Za-z0-9]+)"),
    re.compile(r"yumpu\.com/[a-z]{2}/document/view/\d+/([A-Za-z0-9]+)"),
    re.compile(r'data-yumpu[^=]*=["\']([A-Za-z0-9]+)["\']', re.IGNORECASE),
]


def extract_yumpu_id(article_html: str) -> Optional[str]:
    for pattern in YUMPU_PATTERNS:
        m = pattern.search(article_html)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Paso 3: Bajar imágenes de las páginas del visor de Yumpu
# ---------------------------------------------------------------------------

def download_page_image(yumpu_id: str, page_num: int, session: requests.Session,
                        dest_dir: Path) -> Optional[Path]:
    """
    Intenta bajar una página específica probando los templates de mayor a
    menor resolución. Devuelve la ruta al JPG o None si todos fallan.
    """
    for tmpl in YUMPU_IMG_TEMPLATES:
        url = tmpl.format(doc_id=yumpu_id, page=page_num)
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                dest = dest_dir / f"page_{page_num:02d}.jpg"
                dest.write_bytes(r.content)
                log.debug("Página %d guardada (%s): %d bytes",
                          page_num, tmpl.split("/")[-2], len(r.content))
                return dest
            log.debug("Template falló para página %d: status=%d", page_num, r.status_code)
        except requests.RequestException as e:
            log.debug("Error de red página %d: %s", page_num, e)
    return None


def download_all_pages(yumpu_id: str, session: requests.Session, dest_dir: Path) -> list[Path]:
    """
    Baja páginas secuencialmente hasta que dos consecutivas fallen
    (señal de fin del documento) o llegar a MAX_PAGES.
    """
    pages: list[Path] = []
    consecutive_failures = 0

    for page_num in range(1, MAX_PAGES + 1):
        img_path = download_page_image(yumpu_id, page_num, session, dest_dir)
        if img_path is None:
            consecutive_failures += 1
            log.info("Página %d no disponible (fallo consecutivo %d)",
                     page_num, consecutive_failures)
            if consecutive_failures >= MAX_404_RETRY:
                break
            continue
        consecutive_failures = 0
        pages.append(img_path)

    log.info("Total páginas descargadas: %d", len(pages))
    return pages


# ---------------------------------------------------------------------------
# Paso 4: OCR de las imágenes
# ---------------------------------------------------------------------------

def ocr_images(image_paths: list[Path]) -> str:
    """OCR español sobre cada imagen, concatenado por página."""
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
            log.debug("Página %d: %d chars de texto OCR", i, len(text))
        except Exception as e:
            log.warning("OCR falló en página %d (%s): %s", i, path.name, e)
            pieces.append(f"--- PAGE {i} ({path.name}) — OCR ERROR: {e} ---")

    return "\n\n".join(pieces)


# ---------------------------------------------------------------------------
# Paso 5: Parsear picks del texto OCR
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
        if len(line) < 10 or len(line) > 200:
            continue
        if line.startswith("--- PAGE"):
            continue

        sport = _classify_line(line)
        if sport is None:
            continue

        teams = MLB_TEAMS if sport == "MLB" else NBA_TEAMS
        found = [t for t in teams if t in line]
        matchup = " vs ".join(found[:2]) if len(found) >= 2 else (found[0] if found else "?")

        picks.append(GuiaPick(
            sport=sport,
            matchup=matchup,
            pick=line,
            raw_line=raw,
        ))

    log.info("Picks extraídos: %d MLB, %d NBA",
             sum(1 for p in picks if p.sport == "MLB"),
             sum(1 for p in picks if p.sport == "NBA"))
    return picks


# ---------------------------------------------------------------------------
# Orquestador público
# ---------------------------------------------------------------------------

def fetch_guia(target_date: Optional[date] = None,
               work_dir: Optional[Path] = None) -> GuiaResult:
    if target_date is None:
        target_date = datetime.now().date()
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="listin_guia_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    result = GuiaResult(fecha=target_date, article_url="", yumpu_id=None)
    session = _session()

    # 1. Encontrar artículo
    article_url = find_article_url(target_date, session)
    if not article_url:
        result.error = "no_article_found"
        return result
    result.article_url = article_url

    # 2. ID de Yumpu
    try:
        r = session.get(article_url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        result.error = f"article_fetch_failed: {e}"
        return result

    yumpu_id = extract_yumpu_id(r.text)
    if not yumpu_id:
        result.error = "no_yumpu_id_in_article"
        return result
    result.yumpu_id = yumpu_id

    # 3. Bajar imágenes de páginas
    pages_dir = work_dir / f"pages_{target_date.isoformat()}_{yumpu_id}"
    pages_dir.mkdir(exist_ok=True)
    page_images = download_all_pages(yumpu_id, session, pages_dir)
    result.pages_downloaded = len(page_images)

    if not page_images:
        result.error = "no_pages_downloaded"
        return result

    # 4. OCR
    try:
        ocr_text = ocr_images(page_images)
    except Exception as e:
        log.exception("OCR falló")
        result.error = f"ocr_failed: {e}"
        return result
    result.ocr_text = ocr_text

    # 5. Parsear picks
    result.picks = parse_picks(ocr_text)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    res = fetch_guia()
    print(f"\nFecha:    {res.fecha}")
    print(f"URL:      {res.article_url}")
    print(f"Yumpu:    {res.yumpu_id}")
    print(f"Páginas:  {res.pages_downloaded}")
    print(f"Error:    {res.error}")
    print(f"MLB:      {sum(1 for p in res.picks if p.sport == 'MLB')}")
    print(f"NBA:      {sum(1 for p in res.picks if p.sport == 'NBA')}")
