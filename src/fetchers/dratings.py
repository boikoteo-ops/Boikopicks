"""
Fetcher de DRatings - 4ta fuente (algoritmo Elo + ML, diferente filosofia).
Extrae Money Line + datos crudos para Fase 6 futura (Totales / Spread).
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


def get_dratings_predictions(sport='mlb'):
    """
    Retorna predicciones de DRatings para el deporte indicado.

    Returns:
        Lista de dicts con: home, away, home_prob, away_prob,
        home_pitcher, away_pitcher, total_runs, home_runs, away_runs.
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

            results.append({
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
            })
        except (IndexError, AttributeError, ValueError) as e:
            # Si falla una fila, continua con las demas
            continue

    return results


if __name__ == '__main__':
    print("=" * 60)
    print("TEST FETCHER DRATINGS - MLB")
    print("=" * 60)

    picks = get_dratings_predictions('mlb')
    print(f"\nTotal predicciones: {len(picks)}\n")

    for p in picks:
        pick_team = p['home'] if p['home_prob'] > p['away_prob'] else p['away']
        pick_prob = max(p['home_prob'], p['away_prob'])

        print(f"[{p['away']} @ {p['home']}]")
        print(f"  Modelo: home {p['home_prob']}% | away {p['away_prob']}%")
        print(f"  Pick: {pick_team} ({pick_prob}%)")
        print(f"  Pitchers: {p['away_pitcher']} vs {p['home_pitcher']}")
        print(f"  Runs expected: away {p['away_runs_expected']} | home {p['home_runs_expected']}")
        print(f"  Total runs: {p['total_runs']}")
        if p['away_odds_best']:
            print(f"  Best ML: away {p['away_odds_best']:+d} | home {p['home_odds_best']:+d}")
        print()