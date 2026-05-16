"""
Obtiene la cartelera de MLB de hoy desde la API oficial de MLB.
"""
import requests
from datetime import datetime
import pytz


def get_mlb_games_today():
    """
    Retorna una lista de juegos de MLB programados para hoy.
    Cada juego incluye: id, home, away, hora, pitchers probables.
    """
    # Fecha de hoy en zona horaria de Santo Domingo
    tz = pytz.timezone('America/Santo_Domingo')
    today = datetime.now(tz).strftime('%Y-%m-%d')

    url = f"https://statsapi.mlb.com/api/v1/schedule"
    params = {
        'sportId': 1,
        'date': today,
        'hydrate': 'probablePitcher,team'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener cartelera MLB: {e}")
        return []

    games = []
    for date_entry in data.get('dates', []):
        for game in date_entry.get('games', []):
            if game.get('status', {}).get('abstractGameState') == 'Final':
                continue  # Ignorar juegos ya terminados

            home_team = game['teams']['home']['team']['name']
            away_team = game['teams']['away']['team']['name']

            home_pitcher = game['teams']['home'].get('probablePitcher', {})
            away_pitcher = game['teams']['away'].get('probablePitcher', {})

            game_time_utc = game['gameDate']
            game_time = datetime.fromisoformat(game_time_utc.replace('Z', '+00:00'))
            game_time_local = game_time.astimezone(tz)

            games.append({
                'id': game['gamePk'],
                'sport': 'MLB',
                'home': home_team,
                'away': away_team,
                'start_time': game_time_local.strftime('%I:%M %p'),
                'start_time_iso': game_time_local.isoformat(),
                'home_pitcher': home_pitcher.get('fullName', 'TBD'),
                'away_pitcher': away_pitcher.get('fullName', 'TBD'),
                'venue': game.get('venue', {}).get('name', 'N/A'),
            })

    return games


if __name__ == '__main__':
    games = get_mlb_games_today()
    print(f"\n=== Juegos MLB hoy: {len(games)} ===\n")
    for g in games:
        print(f"{g['start_time']} - {g['away']} @ {g['home']}")
        print(f"  Pitchers: {g['away_pitcher']} vs {g['home_pitcher']}")
        print()
