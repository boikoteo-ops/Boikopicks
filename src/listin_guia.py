"""
listin_guia.py — Quinta fuente de picks: Guía Deportiva del Listín Diario.

Flujo:
  1. Buscar el artículo de la Guía Deportiva del día en listindiario.com
  2. Extraer el ID del documento de Yumpu embebido
  3. Descargar el PDF desde Yumpu
  4. OCR del PDF (Tesseract español, las páginas son escaneos del periódico)
  5. Parsear el texto para extraer picks de MLB y NBA

Dependencias del SO (Ubuntu en GitHub Actions):
    sudo apt-get install -y tesseract-ocr tesseract-ocr-spa poppler-utils

Dependencias Python (agregar a requirements.txt):
    requests
    beautifulsoup4
    pdf2image
    pytesseract
    Pillow
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
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

# Yumpu expone los PDFs aquí. El patrón observado funciona para documentos públicos.
YUMPU_PDF_TEMPLATE = "https://www.yumpu.com/es/document/pdf/{doc_id}.pdf"
YUMPU_EMBED_TEMPLATE = "https://www.yumpu.com/es/embed/view/{doc_id}"


@dataclass
class GuiaPick:
    """Un pick individual extraído de la Guía."""
    sport: str            # "MLB" | "NBA"
    matchup: str          # "Yankees vs Red Sox"
    pick: str             # texto crudo del pick (equipo, línea, etc.)
    raw_line: str         # línea original del OCR (para debug)


@dataclass
class GuiaResult:
    """Resultado completo de la extracción del día."""
    fecha: date
    article_url: str
    yumpu_id: Optional[str]
    pdf_path: Optional[Path]
    picks: list[GuiaPick] = field(default_factory=list)
    ocr_text: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Forma compatible con el resto de fuentes del pipeline."""
        return {
            "source": "listin_guia",
            "fecha": self.fecha.isoformat(),
            "url": self.article_url,
            "yumpu_id": self.yumpu_id,
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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
    })
    return s


# ---------------------------------------------------------------------------
# Paso 1: Encontrar el artículo del día
# ---------------------------------------------------------------------------

def find_article_url(target_date: date, session: requests.Session) -> Optional[str]:
    """
    Busca en el índice de la Guía Deportiva el artículo de la fecha dada.

    Las URLs tienen el formato:
        /el-deporte/guia-deportiva/20260516/gui-deportiva-16-05-2026_905918.html

    Recorre las primeras 2 páginas del índice (suficiente para los últimos ~10 días).
    """
    date_token = target_date.strftime("%Y%m%d")           # 20260516
    date_token_dashed = target_date.strftime("%d-%m-%Y")  # 16-05-2026

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
# Paso 3: Descargar el PDF de Yumpu
# ---------------------------------------------------------------------------

def download_pdf(yumpu_id: str, session: requests.Session, dest: Path) -> Optional[Path]:
    """
    Intenta bajar el PDF directo. Si Yumpu requiere login para descarga,
    devuelve None y el caller tendrá que recurrir al fallback de imágenes
    de las páginas (no implementado aquí — agregar si fuera necesario).
    """
    pdf_url = YUMPU_PDF_TEMPLATE.format(doc_id=yumpu_id)
    try:
        r = session.get(pdf_url, timeout=REQUEST_TIMEOUT, stream=True)
        # Yumpu a veces responde 200 con HTML de login en vez del PDF
        ctype = r.headers.get("Content-Type", "")
        if r.status_code != 200 or "pdf" not in ctype.lower():
            log.warning("PDF directo no disponible (status=%d, ctype=%s)", r.status_code, ctype)
            return None

        dest.write_bytes(r.content)
        log.info("PDF guardado: %s (%d bytes)", dest, dest.stat().st_size)
        return dest
    except requests.RequestException as e:
        log.error("Error bajando PDF: %s", e)
        return None


# ---------------------------------------------------------------------------
# Paso 4: OCR del PDF
# ---------------------------------------------------------------------------

def ocr_pdf(pdf_path: Path) -> str:
    """
    Convierte cada página a imagen y le pasa Tesseract en español.
    Requiere poppler-utils + tesseract-ocr-spa instalados en el sistema.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise RuntimeError(
            "Faltan dependencias: pip install pdf2image pytesseract Pillow"
        ) from e

    # 300 dpi da buen balance precisión/velocidad para periódico impreso.
    images = convert_from_path(str(pdf_path), dpi=300)
    log.info("PDF tiene %d páginas, ejecutando OCR...", len(images))

    pieces = []
    for i, img in enumerate(images, 1):
        text = pytesseract.image_to_string(img, lang="spa")
        pieces.append(f"--- PAGE {i} ---\n{text}")
        log.debug("Página %d: %d chars de texto OCR", i, len(text))

    return "\n\n".join(pieces)


# ---------------------------------------------------------------------------
# Paso 5: Parsear picks del texto OCR
# ---------------------------------------------------------------------------

# La Guía Deportiva del Listín publica picks en formato variable según la edición,
# pero suele incluir bloques de "Grandes Ligas" / "MLB" y "NBA" con líneas tipo:
#   "Yankees -1.5 sobre Red Sox"
#   "Lakers ML vs Warriors"
#   "Más de 8.5 carreras: Dodgers vs Padres"
#
# Los patrones abajo son punto de partida — habrá que ajustarlos después de ver
# OCR real de varios días.

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
    """Devuelve 'MLB', 'NBA' o None según qué equipos aparezcan."""
    line_lower = line
    mlb_hits = sum(1 for t in MLB_TEAMS if t in line_lower)
    nba_hits = sum(1 for t in NBA_TEAMS if t in line_lower)
    if mlb_hits >= 1 and mlb_hits >= nba_hits:
        return "MLB"
    if nba_hits >= 1:
        return "NBA"
    return None


def parse_picks(ocr_text: str) -> list[GuiaPick]:
    """
    Extrae picks línea por línea. Heurística simple — mejorar tras ver outputs reales.
    Devuelve solo líneas que mencionan al menos un equipo de MLB o NBA.
    """
    picks: list[GuiaPick] = []
    for raw in ocr_text.splitlines():
        line = raw.strip()
        if len(line) < 10 or len(line) > 200:
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

def fetch_guia(target_date: Optional[date] = None, work_dir: Optional[Path] = None) -> GuiaResult:
    """
    Punto de entrada del módulo. Llamar así desde main.py:

        from listin_guia import fetch_guia
        result = fetch_guia()
        sources["listin_guia"] = result.to_dict()
    """
    if target_date is None:
        target_date = datetime.now().date()
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="listin_guia_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    result = GuiaResult(fecha=target_date, article_url="", yumpu_id=None, pdf_path=None)
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

    # 3. Descargar PDF
    pdf_path = work_dir / f"guia_{target_date.isoformat()}_{yumpu_id}.pdf"
    if not download_pdf(yumpu_id, session, pdf_path):
        result.error = "pdf_download_failed"
        return result
    result.pdf_path = pdf_path

    # 4. OCR
    try:
        ocr_text = ocr_pdf(pdf_path)
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
    print(f"\nFecha: {res.fecha}")
    print(f"URL:   {res.article_url}")
    print(f"Yumpu: {res.yumpu_id}")
    print(f"Error: {res.error}")
    print(f"Picks MLB: {sum(1 for p in res.picks if p.sport == 'MLB')}")
    print(f"Picks NBA: {sum(1 for p in res.picks if p.sport == 'NBA')}")
    print("\n--- Primeras 5 picks ---")
    for p in res.picks[:5]:
        print(f"  [{p.sport}] {p.matchup}: {p.pick}")
