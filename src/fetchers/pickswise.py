"""
Fetcher de Pickswise - 3ra fuente (experts humanos).
Extrae Money Line picks del JSON embebido en __NEXT_DATA__.
"""
import requests
import re
import json


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

URLS = {
    'mlb': 'https://www.pickswise.com/mlb/picks/',
    'nba': 'https://www.pickswise.com/nba/picks/',
}


def _confidence_to_prob(confidence, is_pick=True):
    """
    Convierte confianza (1-5 estrellas) de Pickswise a probabilidad estimada.
    Pickswise no publica probabilidades, asi que usamos confidence como proxy.

    Si is_pick=True: es el equipo que Pickswise pickea (probabilidad alta).
    Si is_pick=False: es el otro equipo (complemento).
    """
    # Picks de Pickswise tienen confidence 1-5; asignamos probabilidad asi:
    confidence_map = {
        1: 53.0,
        2: 55.0,
        3: 58.0,
        4: 62.0,
        5: 67.0,
    }
    pick_prob = confidence_map.get(confidence, 55.0)
    if is_pick:
        return pick_prob
    else:
        return round(100 - pick_prob, 1)


def get_pickswise_picks(sport='mlb'):
    """
    Retorna picks de Money Line de Pickswise para el deporte indicado.

    Returns:
        Lista de dicts con: home, away, pick_team, pick_team_abbr,
        confidence, odds_american, home_prob_pickswise, away_prob_pickswise
    """
    url = URLS.get(sport)
    if not url:
        print(f"  Sport no soportado: {sport}")
        return []

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Error Pickswise {sport}: {e}")
        return []

    html = response.text

    # Extraer JSON de __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        print(f"  Pickswise {sport}: no se encontro __NEXT_DATA__")
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  Pickswise {sport}: JSON decode error: {e}")
        return []

    # Navegar al array de picks
    try:
        games = data['props']['pageProps']['initialState']['sportPredictionsPicks'][f'/{sport}/picks/']
    except KeyError as e:
        print(f"  Pickswise {sport}: estructura JSON cambio (key {e})")
        return []

    results = []

    for game in games:
        home_team = game.get('homeTeam', {})
        away_team = game.get('awayTeam', {})

        home_name = home_team.get('name', '')
        away_name = away_team.get('name', '')
        home_abbr = home_team.get('abbreviation', '')
        away_abbr = away_team.get('abbreviation', '')

        if not home_name or not away_name:
            continue

        # Buscar pick de Money Line
        base_picks = game.get('basePicks', [])
        ml_pick = None
        for bp in base_picks:
            market = bp.get('market', '')
            if market == 'Money Line':
                ml_pick = bp
                break

        if not ml_pick:
            # No tienen Money Line pick para este juego (solo Total o Run Line)
            continue

        outcome = ml_pick.get('outcome', '')
        confidence = ml_pick.get('confidence', 3)
        odds_american = ml_pick.get('oddsAmerican', '')

        # Determinar a quien pickearon
        # outcome viene como "ATL Braves Win" o "TB Rays Win"
        # Necesitamos saber si es home o away
        outcome_upper = outcome.upper()
        is_home_pick = (
            home_abbr.upper() in outcome_upper or
            home_team.get('nickname', '').upper() in outcome_upper
        )
        is_away_pick = (
            away_abbr.upper() in outcome_upper or
            away_team.get('nickname', '').upper() in outcome_upper
        )

        if is_home_pick:
            pick_team = home_name
            home_prob = _confidence_to_prob(confidence, is_pick=True)
            away_prob = _confidence_to_prob(confidence, is_pick=False)
        elif is_away_pick:
            pick_team = away_name
            home_prob = _confidence_to_prob(confidence, is_pick=False)
            away_prob = _confidence_to_prob(confidence, is_pick=True)
        else:
            # No pudimos determinar, skip
            continue

        results.append({
            'home': home_name,
            'away': away_name,
            'home_abbr': home_abbr,
            'away_abbr': away_abbr,
            'pick_team': pick_team,
            'confidence': confidence,
            'odds_american': odds_american,
            'home_prob_pickswise': home_prob,
            'away_prob_pickswise': away_prob,
        })

    return results


if __name__ == '__main__':
    print("=" * 60)
    print("TEST FETCHER PICKSWISE - MLB")
    print("=" * 60)

    picks = get_pickswise_picks('mlb')
    print(f"\nTotal Money Line picks: {len(picks)}\n")

    for p in picks:
        stars = '⭐' * p['confidence']
        print(f"[{p['away_abbr']} @ {p['home_abbr']}] PICK: {p['pick_team']}")
        print(f"  Confianza: {stars} ({p['confidence']}/5)")
        print(f"  Cuota: {p['odds_american']}")
        print(f"  Prob estimada: home={p['home_prob_pickswise']}% | away={p['away_prob_pickswise']}%")
        print()