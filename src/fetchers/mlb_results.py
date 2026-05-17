"""
Fetcher de resultados finales MLB.
Usa la misma API oficial que mlb_schedule.py.
"""
import requests
from datetime import datetime, timedelta
import pytz


def get_mlb_results(date_str=None):
    """
    Retorna resultados finales de MLB para una fecha dada (formato YYYY-MM-DD).
    Si no se pasa fecha, usa AYER (porque hoy puede tener juegos sin terminar).
    """
    if date_str is None:
        tz = pytz.timezone('America/Santo_Domingo')
        yesterday = datetime.now(tz) - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')

    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        'sportId': 1,
        'date': date_str,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error obteniendo resultados MLB: {e}")
        return []

    results = []
    for date_entry in data.get('dates', []):
        for game in date_entry.get('games', []):
            status = game.get('status', {}).get('abstractGameState', '')
            if status != 'Final':
                continue

            home_team = game['teams']['home']['team']['name']
            away_team = game['teams']['away']['team']['name']
            home_score = game['teams']['home'].get('score', 0)
            away_score = game['teams']['away'].get('score', 0)

            winner = home_team if home_score > away_score else away_team

            results.append({
                'game_id': game['gamePk'],
                'sport': 'MLB',
                'date': date_str,
                'home': home_team,
                'away': away_team,
                'home_score': home_score,
                'away_score': away_score,
                'total_runs': home_score + away_score,
                'winner': winner,
                'status': 'Final',
            })

    return results


def get_nba_results(date_str=None):
    """
    Retorna resultados finales de NBA usando API de ESPN.
    """
    if date_str is None:
        tz = pytz.timezone('America/Santo_Domingo')
        yesterday = datetime.now(tz) - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')

    date_compact = date_str.replace('-', '')
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    params = {'dates': date_compact}
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error obteniendo resultados NBA: {e}")
        return []

    results = []
    for event in data.get('events', []):
        state = event.get('status', {}).get('type', {}).get('state', '')
        if state != 'post':
            continue

        competitions = event.get('competitions', [{}])[0]
        competitors = competitions.get('competitors', [])
        if len(competitors) != 2:
            continue

        home = next((c for c in competitors if c.get('homeAway') == 'home'), {})
        away = next((c for c in competitors if c.get('homeAway') == 'away'), {})

        home_team = home.get('team', {}).get('displayName', '')
        away_team = away.get('team', {}).get('displayName', '')
        home_score = int(home.get('score', 0))
        away_score = int(away.get('score', 0))

        winner = home_team if home_score > away_score else away_team

        results.append({
            'game_id': str(event['id']),
            'sport': 'NBA',
            'date': date_str,
            'home': home_team,
            'away': away_team,
            'home_score': home_score,
            'away_score': away_score,
            'total_points': home_score + away_score,
            'winner': winner,
            'status': 'Final',
        })

    return results


if __name__ == '__main__':
    print("\n=== Resultados MLB de AYER ===\n")
    mlb = get_mlb_results()
    print(f"Juegos finalizados: {len(mlb)}\n")
    for r in mlb[:5]:
        print(f"{r['away']} {r['away_score']} - {r['home_score']} {r['home']}")
        print(f"  Ganador: {r['winner']}")
        print()

    print("\n=== Resultados NBA de AYER ===\n")
    nba = get_nba_results()
    print(f"Juegos finalizados: {len(nba)}\n")
    for r in nba[:5]:
        print(f"{r['away']} {r['away_score']} - {r['home_score']} {r['home']}")
        print(f"  Ganador: {r['winner']}")
        print()