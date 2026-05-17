"""
Fetcher de Covers Consensus - probabilidades del publico apostando.
Refleja sentiment del publico, distinto a numberFire que es modelo estadistico.
"""
import re
import requests


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


def _normalize_team_name(short_name):
    short_name = short_name.strip()
    return COVERS_TEAM_MAP.get(short_name, short_name)


def _is_valid_odds(odds_str):
    try:
        num = int(odds_str)
        return -2000 <= num <= 2000 and abs(num) >= 100
    except ValueError:
        return False


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


if __name__ == '__main__':
    print("\n=== Covers Consensus MLB ===\n")
    mlb_picks = get_covers_consensus('mlb')
    print(f"Juegos encontrados: {len(mlb_picks)}\n")
    for g in mlb_picks:
        fav = g['home'] if g['home_pct_public'] > g['away_pct_public'] else g['away']
        fav_pct = max(g['home_pct_public'], g['away_pct_public'])
        print(f"{g['away']} ({g['away_pct_public']}%) @ {g['home']} ({g['home_pct_public']}%)")
        print(f"  Mayoria apuesta a: {fav} ({fav_pct}%)")
        if g['away_odds'] and g['home_odds']:
            print(f"  Cuotas: {g['away_odds']:+d} / {g['home_odds']:+d}")
        print()