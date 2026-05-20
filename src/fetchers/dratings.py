"""
Fetcher de DRatings - 4ta fuente (algoritmo Elo + ML, diferente filosofia).
Extrae Money Line + Totales (O/U vs linea Vegas) para MLB.
"""
import requests
import re
from bs4 import BeautifulSoup


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

URLS = {
    'mlb': 'https://www.dratings.com/predictor/mlb-baseball-predictions/',
    'nba': 'https://www.dratings.com/predictor/nba-basketball-predictions/',
}


def _parse_team_with_record(text):
    """
    Parsea 'Atlanta Braves (32-15) Miami Marlins (21-26)'
    Retorna (home_team, away_team).
    DRatings muestra away primero, luego home.
    """
    # Quitar parentesis con record: '(32-15)'
    clean = re.sub(r'\([^)]*\)', '', text)
    # Limpiar espacios multiples
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def _split_teams(text):
    """
    Recibe 'Atlanta Braves Miami Marlins' (sin records)
    y devuelve tupla (away, home) - DRatings pone away primero.
    Necesitamos un mapping de equipos conocidos.
    """
    return text


# Lista de equipos MLB para identificar boundaries
MLB_TEAMS = [
    'Arizona Diamondbacks', 'Atlanta Braves', 'Baltimore Orioles',
    'Boston Red Sox', 'Chicago Cubs', 'Chicago White Sox',
    'Cincinnati Reds', 'Cleveland Guardians', 'Colorado Rockies',
    'Detroit Tigers', 'Houston Astros', 'Kansas City Royals',
    'Los Angeles Angels', 'Los Angeles Dodgers', 'Miami Marlins',
    'Milwaukee Brewers', 'Minnesota Twins', 'New York Mets',
    'New York Yankees', 'Philadelphia Phillies', 'Pittsburgh Pirates',
    'San Diego Padres', 'San Francisco Giants', 'Seattle Mariners',
    'St. Louis Cardinals', 'Tampa Bay Rays', 'Texas Rangers',
    'Toronto Blue Jays', 'Washington Nationals', 'Athletics',
]


def _identify_two_teams(text):
    """
    Encuentra los 2 equipos MLB en un texto.
    Retorna (away_team, home_team) - DRatings pone away primero.
    """
    found = []
    for team in MLB_TEAMS:
        idx = text.find(team)
        if idx >= 0:
            found.append((idx, team))

    found.sort()
    teams_ordered = [t for _, t in found]

    if len(teams_ordered) >= 2:
        return teams_ordered[0], teams_ordered[1]  # away, home
    return None, None


def _parse_probabilities(text):
    """
    Parsea '49.6% 50.4%' -> (49.6, 50.4)
    DRatings muestra away_prob | home_prob.
    """
    matches = re.findall(r'(\d+\.\d+)%', text)
    if len(matches) >= 2:
        return float(matches[0]), float(matches[1])
    return None, None


def _parse_total_runs(text):
    """Parsea '8.51' -> 8.51"""
    match = re.search(r'(\d+\.\d+)', text)
    if match:
        return float(match.group(1))
    return None


def _parse_runs_per_team(text):
    """Parsea '4.23 4.28' -> (4.23, 4.28)"""
    matches = re.findall(r'(\d+\.\d+)', text)
    if len(matches) >= 2:
        return float(matches[0]), float(matches[1])
    return None, None


# ---------------------------------------------------------------------------
# NUEVAS funciones para Over/Under (Fase 6 — activada)
# ---------------------------------------------------------------------------

def _parse_ou_line_and_odds(cell):
    """
    Parsea la celda "Best O/U" de DRatings.
    Estructura del HTML (preferimos Vegas, fallback offshore):
        <div class="offshore-sportsbook">o8½+100<br />u8½-114</div>
        <div class="vegas-sportsbook">o8½-105<br />u8½-115</div>

    Devuelve dict {line: float, over_odds: int, under_odds: int, book: str}
    o None si no se puede parsear.

    Notas:
    - "o8½" significa over 8.5 (DRatings usa ½ para fracciones)
    - Las odds vienen con signo: -105 (favorito) o +100 (underdog)
    - Si over y under tienen líneas distintas (ej. "o7 / u7½"), tomamos el
      promedio como línea de referencia.
    """
    # Preferir vegas sobre offshore
    vegas_div = cell.find('div', class_='vegas-sportsbook')
    offshore_div = cell.find('div', class_='offshore-sportsbook')

    div_to_use = None
    book = None
    if vegas_div and vegas_div.get_text(strip=True):
        div_to_use = vegas_div
        book = 'vegas'
    elif offshore_div and offshore_div.get_text(strip=True):
        div_to_use = offshore_div
        book = 'offshore'

    if div_to_use is None:
        return None

    # El texto viene como "o8½-105\nu8½-115" o "o8½-105 u8½-115"
    text = div_to_use.get_text(separator='\n', strip=True)

    # Reemplazar ½ por .5 para parsear como decimal
    text_clean = text.replace('½', '.5').replace('¼', '.25').replace('¾', '.75')

    # Patrón: o<linea><signo><odds> y u<linea><signo><odds>
    # Ej: "o8.5-105", "u9+100"
    over_match = re.search(r'o(\d+(?:\.\d+)?)([+-]\d+)', text_clean)
    under_match = re.search(r'u(\d+(?:\.\d+)?)([+-]\d+)', text_clean)

    if not over_match or not under_match:
        return None

    over_line = float(over_match.group(1))
    over_odds = int(over_match.group(2))
    under_line = float(under_match.group(1))
    under_odds = int(under_match.group(2))

    # Si líneas difieren (raro pero pasa con líneas "movidas"), promediar
    line = (over_line + under_line) / 2 if over_line != under_line else over_line

    return {
        'line': line,
        'over_odds': over_odds,
        'under_odds': under_odds,
        'book': book,
    }


def _calc_ou_pick(total_runs_dratings, ou_data):
    """
    Decide el pick O/U del modelo DRatings comparando su proyeccion
    contra la linea Vegas. Devuelve 'over', 'under' o None.

    Margen minimo de 0.20 carreras para evitar picks borderline cuando
    proyeccion = linea (esos casos son ruido, no senal).
    """
    if total_runs_dratings is None or ou_data is None:
        return None

    line = ou_data['line']
    diff = total_runs_dratings - line

    if diff >= 0.20:
        return 'over'
    elif diff <= -0.20:
        return 'under'
    return None  # Demasiado cerca de la linea, no hay senal


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

def get_dratings_predictions(sport='mlb'):
    """
    Retorna predicciones de DRatings para el deporte indicado.

    Returns:
        Lista de dicts con (todos los campos existentes preservados):
        - Money Line: home, away, home_prob, away_prob, home_pitcher,
          away_pitcher, total_runs, home_runs, away_runs, home_odds_best,
          away_odds_best.
        - NUEVOS (Over/Under): ou_line, ou_over_odds, ou_under_odds,
          ou_book, ou_pick ('over'|'under'|None), ou_diff (carreras
          de diferencia entre proyeccion y linea).
    """
    url = URLS.get(sport)
    if not url:
        print(f"  Sport no soportado: {sport}")
        return []

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Error DRatings {sport}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')

    # Buscar la tabla de "Upcoming Games"
    heading = soup.find('h2', string=re.compile('Upcoming Games', re.IGNORECASE))
    if not heading:
        print(f"  DRatings {sport}: no se encontro tabla 'Upcoming Games'")
        return []

    table = heading.find_next('table')
    if not table:
        print(f"  DRatings {sport}: no hay tabla despues del heading")
        return []

    tbody = table.find('tbody')
    if not tbody:
        print(f"  DRatings {sport}: tabla sin tbody")
        return []

    rows = tbody.find_all('tr')
    results = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 8:
            continue

        try:
            # Cell 1: Teams "Atlanta Braves (32-15) Miami Marlins (21-26)"
            teams_text = cells[1].get_text(separator=' ', strip=True)
            teams_clean = _parse_team_with_record(teams_text)
            away_team, home_team = _identify_two_teams(teams_clean)
            if not away_team or not home_team:
                continue

            # Cell 2: Pitchers "JR Ritchie | Max Meyer" (away | home)
            pitchers_text = cells[2].get_text(separator='|', strip=True)
            pitcher_parts = [p.strip() for p in pitchers_text.split('|') if p.strip()]
            away_pitcher = pitcher_parts[0] if len(pitcher_parts) > 0 else None
            home_pitcher = pitcher_parts[1] if len(pitcher_parts) > 1 else None

            # Cell 3: Win probs "49.6% 50.4%" (away | home)
            probs_text = cells[3].get_text(separator=' ', strip=True)
            away_prob, home_prob = _parse_probabilities(probs_text)
            if away_prob is None or home_prob is None:
                continue

            # Cell 6: Runs per team "4.23 4.28"
            runs_text = cells[6].get_text(separator=' ', strip=True)
            away_runs, home_runs = _parse_runs_per_team(runs_text)

            # Cell 7: Total runs "8.51"
            total_runs = _parse_total_runs(cells[7].get_text(strip=True))

            # Best ML odds (cell 4) - opcional
            best_ml_text = cells[4].get_text(separator=' ', strip=True)
            ml_matches = re.findall(r'([+-]\d+)', best_ml_text)
            away_odds = int(ml_matches[0]) if len(ml_matches) > 0 else None
            home_odds = int(ml_matches[1]) if len(ml_matches) > 1 else None

            # NUEVO Cell 8: Best O/U "o8½-105 / u8½-115"
            ou_data = None
            if len(cells) >= 9:
                ou_data = _parse_ou_line_and_odds(cells[8])

            # NUEVO Pick O/U calculado: proyeccion DRatings vs linea Vegas
            ou_pick = _calc_ou_pick(total_runs, ou_data)
            ou_diff = None
            if total_runs is not None and ou_data is not None:
                ou_diff = round(total_runs - ou_data['line'], 2)

            results.append({
                # === Money Line (campos existentes — sin cambios) ===
                'home': home_team,
                'away': away_team,
                'home_prob': home_prob,
                'away_prob': away_prob,
                'home_pitcher': home_pitcher,
                'away_pitcher': away_pitcher,
                'home_runs_expected': home_runs,
                'away_runs_expected': away_runs,
                'total_runs': total_runs,
                'home_odds_best': home_odds,
                'away_odds_best': away_odds,
                # === Over/Under (NUEVOS — Fase 6) ===
                'ou_line': ou_data['line'] if ou_data else None,
                'ou_over_odds': ou_data['over_odds'] if ou_data else None,
                'ou_under_odds': ou_data['under_odds'] if ou_data else None,
                'ou_book': ou_data['book'] if ou_data else None,
                'ou_pick': ou_pick,
                'ou_diff': ou_diff,
            })
        except (IndexError, AttributeError, ValueError) as e:
            # Si falla una fila, continua con las demas
            continue

    return results


if __name__ == '__main__':
    print("=" * 60)
    print("TEST FETCHER DRATINGS - MLB (con O/U)")
    print("=" * 60)

    picks = get_dratings_predictions('mlb')
    print(f"\nTotal predicciones: {len(picks)}\n")

    ou_count = sum(1 for p in picks if p['ou_pick'] is not None)
    print(f"Picks O/U generados: {ou_count} de {len(picks)} juegos\n")

    for p in picks:
        pick_team = p['home'] if p['home_prob'] > p['away_prob'] else p['away']
        pick_prob = max(p['home_prob'], p['away_prob'])

        print(f"[{p['away']} @ {p['home']}]")
        print(f"  ML pick: {pick_team} ({pick_prob}%)")
        print(f"  Pitchers: {p['away_pitcher']} vs {p['home_pitcher']}")
        print(f"  Runs proyectados: away {p['away_runs_expected']} | home {p['home_runs_expected']} | total {p['total_runs']}")
        if p['away_odds_best']:
            print(f"  Best ML: away {p['away_odds_best']:+d} | home {p['home_odds_best']:+d}")
        # NUEVO bloque O/U
        if p['ou_line'] is not None:
            arrow = '▲' if p['ou_pick'] == 'over' else ('▼' if p['ou_pick'] == 'under' else '—')
            pick_str = p['ou_pick'].upper() if p['ou_pick'] else 'PASS (muy cerca)'
            print(f"  O/U: linea {p['ou_line']} ({p['ou_book']}) | over {p['ou_over_odds']:+d} / under {p['ou_under_odds']:+d}")
            print(f"       {arrow} Pick: {pick_str} (proyeccion {p['total_runs']} vs linea {p['ou_line']}, diff {p['ou_diff']:+.2f})")
        else:
            print(f"  O/U: linea no disponible")
        print()
