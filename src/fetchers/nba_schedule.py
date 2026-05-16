"""
Obtiene la cartelera de NBA de hoy.
Usa balldontlie.io y ESPN como fuentes.
"""
import requests
from datetime import datetime
import pytz


def _try_balldontlie(today_str):
    url = "https://www.balldontlie.io/api/v1/games"
    params = {
        'start_date': today_str,
        'end_date': today_str,
        'per_page': 100
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get('data', [])
    except requests.exceptions.RequestException:
        return None


def _try_espn(today_str):
    date_compact = today_str.replace('-', '')
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    params = {'dates': date_compact}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get('events', [])
    except requests.exceptions.RequestException:
        return None


def get_nba_games_today():
    tz = pytz.timezone('America/Santo_Domingo')
    today_str = datetime.now(tz).strftime('%Y-%m-%d')

    games = []

    bdl_games = _try_balldontlie(today_str)
    if bdl_games:
        for game in bdl_games:
            status = game.get('status', '')
            if status == 'Final':
                continue
            games.append({
                'id': str(game['id']),
                'sport': 'NBA',
                'home': game['home_team']['full_name'],
                'away': game['visitor_team']['full_name'],
                'start_time': status if 'PM' in status or 'AM' in status else 'TBD',
                'start_time_iso': game.get('date', ''),
                'home_pitcher': None,
                'away_pitcher': None,
                'venue': 'N/A',
                'game_label': '',
                'series_text': '',
            })
        return games

    espn_events = _try_espn(today_str)
    if espn_events:
        for event in espn_events:
            status = event.get('status', {}).get('type', {}).get('state', '')
            if status == 'post':
                continue

            competitions = event.get('competitions', [{}])[0]
            competitors = competitions.get('competitors', [])
            if len(competitors) != 2:
                continue

            home_team = next((c for c in competitors if c.get('homeAway') == 'home'), {})
            away_team = next((c for c in competitors if c.get('homeAway') == 'away'), {})

            game_time_utc = event.get('date', '')
            try:
                game_time = datetime.fromisoformat(game_time_utc.replace('Z', '+00:00'))
                game_time_local = game_time.astimezone(tz)
                start_time = game_time_local.strftime('%I:%M %p')
                start_time_iso = game_time_local.isoformat()
            except (ValueError, AttributeError):
                start_time = 'TBD'
                start_time_iso = ''

            games.append({
                'id': str(event['id']),
                'sport': 'NBA',
                'home': home_team.get('team', {}).get('displayName', ''),
                'away': away_team.get('team', {}).get('displayName', ''),
                'start_time': start_time,
                'start_time_iso': start_time_iso,
                'home_pitcher': None,
                'away_pitcher': None,
                'venue': competitions.get('venue', {}).get('fullName', 'N/A'),
                'game_label': event.get('name', ''),
                'series_text': '',
            })
        return games

    print("No se pudo obtener cartelera NBA de ninguna fuente.")
    return []


if __name__ == '__main__':
    games = get_nba_games_today()
    print(f"\n=== Juegos NBA hoy: {len(games)} ===\n")
    if not games:
        print("No hay juegos NBA programados para hoy.")
    for g in games:
        print(f"{g['start_time']} - {g['away']} @ {g['home']}")
        if g['venue'] != 'N/A':
            print(f"  Arena: {g['venue']}")
        print()