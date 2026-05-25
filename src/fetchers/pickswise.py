"""
Fetcher de Pickswise - 3ra fuente (experts humanos).
Extrae Money Line picks Y Game Totals picks del JSON embebido en __NEXT_DATA__.
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


def _fetch_and_parse_json(sport):
    """
    Helper compartido: descarga la pagina y devuelve el array de juegos.
    Centraliza la logica de red para que ML y Totals la reusen sin duplicar.

    Retorna lista de game dicts (raw JSON) o None si falla.
    """
    url = URLS.get(sport)
    if not url:
        print(f"  Sport no soportado: {sport}")
        return None

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Error Pickswise {sport}: {e}")
        return None

    html = response.text

    # Extraer JSON de __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        print(f"  Pickswise {sport}: no se encontro __NEXT_DATA__")
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  Pickswise {sport}: JSON decode error: {e}")
        return None

    # Navegar al array de picks
    try:
        games = data['props']['pageProps']['initialState']['sportPredictionsPicks'][f'/{sport}/picks/']
        return games
    except KeyError as e:
        print(f"  Pickswise {sport}: estructura JSON cambio (key {e})")
        return None


def get_pickswise_picks(sport='mlb'):
    """
    Retorna picks de Money Line de Pickswise para el deporte indicado.
    SIN CAMBIOS respecto a la version anterior.

    Returns:
        Lista de dicts con: home, away, pick_team, pick_team_abbr,
        confidence, odds_american, home_prob_pickswise, away_prob_pickswise
    """
    games = _fetch_and_parse_json(sport)
    if games is None:
        return []

    results = []

    for game in games:
        # FIX: la API a veces retorna explicitamente null en homeTeam/awayTeam
        # (juegos TBD, allstar, playoffs sin matchup confirmado). El `or {}` cubre
        # el caso null porque .get('homeTeam', {}) retorna None si el valor es null.
        home_team = game.get('homeTeam') or {}
        away_team = game.get('awayTeam') or {}

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


# ---------------------------------------------------------------------------
# NUEVA funcion: Game Totals (Over/Under)
# ---------------------------------------------------------------------------

def _parse_outcome_totals(outcome):
    """
    Parsea el outcome de un pick de Game Totals.
    Ejemplos observados:
        'Over 10.5'   -> ('over', 10.5)
        'Under 10'    -> ('under', 10.0)
        'Under 9.0'   -> ('under', 9.0)
        'Over 8.5'    -> ('over', 8.5)

    Devuelve (pick, line) o (None, None) si no se puede parsear.
    """
    if not outcome:
        return None, None

    m = re.match(r'^\s*(over|under)\s+(\d+(?:\.\d+)?)\s*$', outcome.strip(), re.IGNORECASE)
    if not m:
        return None, None

    pick = m.group(1).lower()
    line = float(m.group(2))
    return pick, line


def get_pickswise_totals(sport='mlb'):
    """
    Retorna picks de Game Totals (Over/Under) de Pickswise para el deporte indicado.

    NUEVA funcion (Fase 6 — totales). Es paralela a get_pickswise_picks,
    no la reemplaza. Reusa el mismo fetch HTTP (una sola descarga si se llaman
    consecutivamente, pero el cache es del lado del sistema operativo / HTTP).

    Pickswise da UN solo pick por juego (ML, Total o Run Line). Esta funcion
    devuelve solo los juegos donde el pick es Game Totals — los de ML los
    ignora (esos los maneja get_pickswise_picks).

    Returns:
        Lista de dicts con:
            home, away, home_abbr, away_abbr,
            ou_pick ('over' | 'under'),
            ou_line (float, ej 8.5),
            ou_confidence (1-5),
            ou_odds_american (str, ej '-110'),
            ou_prob_pickswise (probabilidad implicita estimada via confidence)
    """
    games = _fetch_and_parse_json(sport)
    if games is None:
        return []

    results = []

    for game in games:
        # FIX: mismo patron defensivo que en get_pickswise_picks (homeTeam puede ser None)
        home_team = game.get('homeTeam') or {}
        away_team = game.get('awayTeam') or {}

        home_name = home_team.get('name', '')
        away_name = away_team.get('name', '')
        home_abbr = home_team.get('abbreviation', '')
        away_abbr = away_team.get('abbreviation', '')

        if not home_name or not away_name:
            continue

        # Buscar pick de Game Totals
        base_picks = game.get('basePicks', [])
        total_pick = None
        for bp in base_picks:
            market = bp.get('market', '')
            if market == 'Game Totals':
                total_pick = bp
                break

        if not total_pick:
            # Este juego no tiene pick de Total (puede tener ML o Run Line)
            continue

        outcome = total_pick.get('outcome', '')
        confidence = total_pick.get('confidence', 3)
        odds_american = total_pick.get('oddsAmerican', '')
        # Pickswise tambien expone 'line' directamente como numero
        line_from_json = total_pick.get('line')

        # Parsear outcome ('Over 10.5' / 'Under 9.0')
        ou_pick, line_from_outcome = _parse_outcome_totals(outcome)
        if ou_pick is None:
            # No pudimos parsear el outcome, skip
            continue

        # Preferir el campo 'line' del JSON si existe, fallback al parseado
        line = line_from_json if line_from_json is not None else line_from_outcome

        # Probabilidad implicita estimada via confianza (mismo mapeo que ML)
        ou_prob = _confidence_to_prob(confidence, is_pick=True)

        results.append({
            'home': home_name,
            'away': away_name,
            'home_abbr': home_abbr,
            'away_abbr': away_abbr,
            'ou_pick': ou_pick,
            'ou_line': float(line) if line is not None else None,
            'ou_confidence': confidence,
            'ou_odds_american': odds_american,
            'ou_prob_pickswise': ou_prob,
        })

    return results


if __name__ == '__main__':
    print("=" * 60)
    print("TEST FETCHER PICKSWISE - MLB")
    print("=" * 60)

    print("\n--- Money Line picks ---")
    ml_picks = get_pickswise_picks('mlb')
    print(f"Total ML picks: {len(ml_picks)}\n")

    for p in ml_picks:
        stars = '*' * p['confidence']
        print(f"[{p['away_abbr']} @ {p['home_abbr']}] PICK: {p['pick_team']}")
        print(f"  Confianza: {stars} ({p['confidence']}/5) | Cuota: {p['odds_american']}")
        print(f"  Prob estimada: home={p['home_prob_pickswise']}% | away={p['away_prob_pickswise']}%")
        print()

    print("\n--- Game Totals picks (NUEVO) ---")
    ou_picks = get_pickswise_totals('mlb')
    print(f"Total O/U picks: {len(ou_picks)}\n")

    for p in ou_picks:
        stars = '*' * p['ou_confidence']
        arrow = '^' if p['ou_pick'] == 'over' else 'v'
        print(f"[{p['away_abbr']} @ {p['home_abbr']}] {arrow} {p['ou_pick'].upper()} {p['ou_line']}")
        print(f"  Confianza: {stars} ({p['ou_confidence']}/5) | Cuota: {p['ou_odds_american']}")
        print(f"  Prob estimada: {p['ou_prob_pickswise']}%")
        print()
