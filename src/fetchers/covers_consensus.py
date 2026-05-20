"""
Fetcher de Covers Consensus - probabilidades del publico apostando.
Refleja sentiment del publico, distinto a numberFire que es modelo estadistico.

Expone:
- get_covers_consensus(sport) : Money Line picks (sin cambios)
- get_covers_totals(sport)    : Over/Under picks (Fase 6 — nuevo)
"""
import re
import requests
from bs4 import BeautifulSoup


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


COVERS_TEAM_MAP = {
    'Toronto': 'Toronto Blue Jays',
    'Detroit': 'Detroit Tigers',
    'Kansas City': 'Kansas City Royals',
    'St. Louis': 'St. Louis Cardinals',
    'Arizona': 'Arizona Diamondbacks',
    'Colorado': 'Colorado Rockies',
    'Philadelphia': 'Philadelphia Phillies',
    'Pittsburgh': 'Pittsburgh Pirates',
    'Baltimore': 'Baltimore Orioles',
    'Washington': 'Washington Nationals',
    'Miami': 'Miami Marlins',
    'Tampa Bay': 'Tampa Bay Rays',
    'Cincinnati': 'Cincinnati Reds',
    'Cleveland': 'Cleveland Guardians',
    'Chi. Cubs': 'Chicago Cubs',
    'Chi. White Sox': 'Chicago White Sox',
    'Texas': 'Texas Rangers',
    'Houston': 'Houston Astros',
    'Milwaukee': 'Milwaukee Brewers',
    'Minnesota': 'Minnesota Twins',
    'Boston': 'Boston Red Sox',
    'Atlanta': 'Atlanta Braves',
    'San Diego': 'San Diego Padres',
    'Seattle': 'Seattle Mariners',
    'NY Yankees': 'New York Yankees',
    'NY Mets': 'New York Mets',
    'LA Dodgers': 'Los Angeles Dodgers',
    'LA Angels': 'Los Angeles Angels',
    'San Francisco': 'San Francisco Giants',
    'Athletics': 'Athletics',
}


# ---------------------------------------------------------------------------
# Mapping de abreviaciones (Covers usa 'Nym', 'Was', 'Chc'...) a nombres
# completos. Esto es necesario en la pagina O/U porque los `title=` solo dan
# nombres cortos ambiguos (ej: 'New York' aplica para Mets y Yankees).
# ---------------------------------------------------------------------------
COVERS_ABBR_MAP = {
    'ari': 'Arizona Diamondbacks',
    'atl': 'Atlanta Braves',
    'bal': 'Baltimore Orioles',
    'bos': 'Boston Red Sox',
    'chc': 'Chicago Cubs',
    'chw': 'Chicago White Sox',
    'cin': 'Cincinnati Reds',
    'cle': 'Cleveland Guardians',
    'col': 'Colorado Rockies',
    'det': 'Detroit Tigers',
    'hou': 'Houston Astros',
    'kc':  'Kansas City Royals',
    'kcr': 'Kansas City Royals',
    'laa': 'Los Angeles Angels',
    'lad': 'Los Angeles Dodgers',
    'mia': 'Miami Marlins',
    'mil': 'Milwaukee Brewers',
    'min': 'Minnesota Twins',
    'nym': 'New York Mets',
    'nyy': 'New York Yankees',
    'phi': 'Philadelphia Phillies',
    'pit': 'Pittsburgh Pirates',
    'sd':  'San Diego Padres',
    'sdp': 'San Diego Padres',
    'sea': 'Seattle Mariners',
    'sf':  'San Francisco Giants',
    'sfg': 'San Francisco Giants',
    'stl': 'St. Louis Cardinals',
    'tb':  'Tampa Bay Rays',
    'tbr': 'Tampa Bay Rays',
    'tex': 'Texas Rangers',
    'tor': 'Toronto Blue Jays',
    'was': 'Washington Nationals',
    'wsn': 'Washington Nationals',
    'ath': 'Athletics',
    'oak': 'Athletics',
    # Fallbacks por si Covers usa variantes
    'az':  'Arizona Diamondbacks',
}


def _normalize_team_name(short_name):
    short_name = short_name.strip()
    return COVERS_TEAM_MAP.get(short_name, short_name)


def _abbr_to_full(abbr):
    """Convierte abreviacion Covers (ej. 'Nym', 'Chc') a nombre completo."""
    if not abbr:
        return None
    return COVERS_ABBR_MAP.get(abbr.lower().strip())


def _is_valid_odds(odds_str):
    try:
        num = int(odds_str)
        return -2000 <= num <= 2000 and abs(num) >= 100
    except ValueError:
        return False


# ===========================================================================
# Money Line (sin cambios respecto a la version anterior)
# ===========================================================================

def _parse_covers_html(html, sport):
    rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)

    games = []
    for row in rows:
        teams = re.findall(r'title="([A-Z][a-zA-Z .]+?)"', row)
        if len(teams) < 2:
            continue

        pcts = re.findall(r'(\d+)\s*%', row)
        if len(pcts) < 2:
            continue

        all_numbers = re.findall(r'([+-]\d{3,4})', row)
        valid_odds = [int(o) for o in all_numbers if _is_valid_odds(o)]
        if len(valid_odds) < 2:
            continue

        away_short = teams[0]
        home_short = teams[1]
        away_pct = int(pcts[0])
        home_pct = int(pcts[1])

        if abs((away_pct + home_pct) - 100) > 2:
            continue

        away_full = _normalize_team_name(away_short)
        home_full = _normalize_team_name(home_short)

        games.append({
            'sport': sport,
            'home': home_full,
            'away': away_full,
            'home_pct_public': float(home_pct),
            'away_pct_public': float(away_pct),
            'away_odds': valid_odds[0] if len(valid_odds) >= 1 else None,
            'home_odds': valid_odds[1] if len(valid_odds) >= 2 else None,
            'source': 'Covers Consensus',
        })

    return games


def get_covers_consensus(sport='mlb'):
    """Money Line consensus (sin cambios)."""
    url = f"https://contests.covers.com/consensus/topconsensus/{sport}/overall"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"  Covers {sport.upper()} respondio {response.status_code}")
            return []
        return _parse_covers_html(response.text, sport.upper())
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching Covers {sport.upper()}: {e}")
        return []


# ===========================================================================
# Over/Under (NUEVA - Fase 6)
# ===========================================================================

def _parse_ou_cell(cell):
    """
    Parsea celda 2 de la tabla O/U.

    Estructura HTML observada:
        <span class="...consensusTable--high">
            <span>75 % Over</span>
        </span>
        <br/>
        <span class="...consensusTable--low">
            <span>25 % Under</span>
        </span>

    El orden Over/Under cambia: a veces "75% Over" esta en --high,
    a veces "60% Under" esta en --high. La clase --high indica el lado
    mayoritario, --low el minoritario.

    Devuelve (pct_over, pct_under) o (None, None) si no se puede parsear.
    """
    high_span = cell.find('span', class_=re.compile(r'consensusTable--high'))
    low_span  = cell.find('span', class_=re.compile(r'consensusTable--low'))

    if not high_span or not low_span:
        return None, None

    high_text = high_span.get_text(strip=True)
    low_text  = low_span.get_text(strip=True)

    pct_over = None
    pct_under = None

    # Patron: "75 % Over" o "25 % Under"
    for text in (high_text, low_text):
        m = re.match(r'(\d+)\s*%\s*(over|under)', text, re.IGNORECASE)
        if not m:
            continue
        pct = int(m.group(1))
        side = m.group(2).lower()
        if side == 'over':
            pct_over = pct
        else:
            pct_under = pct

    return pct_over, pct_under


def _extract_team_abbrs_from_logo_urls(row):
    """
    Extrae abreviaciones desde las URLs de los logos:
        src="https://img.covers.com/covers/data/logos/mlb/nym.gif"
        src="https://img.covers.com/covers/data/logos/mlb/was.gif"
    Devuelve (away_abbr, home_abbr) — Covers pone away primero (teamBlock),
    home segundo (teamBlock2).
    """
    matches = re.findall(r'/logos/mlb/([a-z]+)\.gif', str(row), re.IGNORECASE)
    if len(matches) >= 2:
        return matches[0].lower(), matches[1].lower()
    return None, None


def _parse_covers_ou_html(html, sport):
    """Parsea la pagina topoverunderconsensus de Covers."""
    soup = BeautifulSoup(html, 'html.parser')

    table = soup.find('table')
    if not table:
        print(f"  Covers O/U {sport.upper()}: no se encontro tabla")
        return []

    rows = table.find_all('tr')
    games = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 4:
            continue  # filas de header u otras

        try:
            # Celda 0: matchup column con logos de ambos equipos
            away_abbr, home_abbr = _extract_team_abbrs_from_logo_urls(cells[0])
            if not away_abbr or not home_abbr:
                continue

            away_full = _abbr_to_full(away_abbr)
            home_full = _abbr_to_full(home_abbr)
            if not away_full or not home_full:
                # Abreviacion desconocida; skip pero loggear para detectar
                print(f"  Covers O/U: abbr desconocida ({away_abbr} / {home_abbr})")
                continue

            # Celda 2: % Over / % Under
            pct_over, pct_under = _parse_ou_cell(cells[2])
            if pct_over is None or pct_under is None:
                continue
            # Sanity: deben sumar ~100
            if abs((pct_over + pct_under) - 100) > 2:
                continue

            # Celda 3: linea numerica (ej "9.5" o "10")
            line_text = cells[3].get_text(strip=True)
            line_match = re.match(r'(\d+(?:\.\d+)?)', line_text)
            if not line_match:
                continue
            line = float(line_match.group(1))

            # Determinar pick (mayoria del publico)
            if pct_over > pct_under:
                ou_pick = 'over'
                ou_pct_public = float(pct_over)
            else:
                ou_pick = 'under'
                ou_pct_public = float(pct_under)

            games.append({
                'sport': sport,
                'home': home_full,
                'away': away_full,
                'home_abbr': home_abbr.upper(),
                'away_abbr': away_abbr.upper(),
                'ou_line': line,
                'ou_pct_over': float(pct_over),
                'ou_pct_under': float(pct_under),
                'ou_pick': ou_pick,
                'ou_pct_public': ou_pct_public,  # % del lado pickeado
                'source': 'Covers Consensus (O/U)',
            })
        except (IndexError, AttributeError, ValueError) as e:
            continue

    return games


def get_covers_totals(sport='mlb'):
    """
    Over/Under consensus del publico apostando (NUEVO - Fase 6).

    Returns:
        Lista de dicts con: home, away, home_abbr, away_abbr,
        ou_line, ou_pct_over, ou_pct_under,
        ou_pick ('over' | 'under'), ou_pct_public (% del lado mayoritario)
    """
    url = f"https://contests.covers.com/consensus/topoverunderconsensus/{sport}/overall"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"  Covers O/U {sport.upper()} respondio {response.status_code}")
            return []
        return _parse_covers_ou_html(response.text, sport.upper())
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching Covers O/U {sport.upper()}: {e}")
        return []


if __name__ == '__main__':
    print("=" * 60)
    print("TEST FETCHER COVERS - MLB")
    print("=" * 60)

    print("\n--- Money Line consensus ---")
    ml = get_covers_consensus('mlb')
    print(f"Juegos: {len(ml)}\n")
    for g in ml:
        fav = g['home'] if g['home_pct_public'] > g['away_pct_public'] else g['away']
        print(f"  {g['away']} ({g['away_pct_public']}%) @ {g['home']} ({g['home_pct_public']}%)  -> {fav}")

    print("\n--- Over/Under consensus (NUEVO) ---")
    ou = get_covers_totals('mlb')
    print(f"Juegos: {len(ou)}\n")
    for g in ou:
        arrow = '^' if g['ou_pick'] == 'over' else 'v'
        print(f"  [{g['away_abbr']} @ {g['home_abbr']}]  {arrow} {g['ou_pick'].upper()} {g['ou_line']}  ({g['ou_pct_public']}% publico)")
