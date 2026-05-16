"""
Obtiene cuotas y predicciones de numberFire (via FanDuel Research)
para los juegos MLB y NBA de hoy.
"""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36'
}


def _get_today_str():
    tz = pytz.timezone('America/Santo_Domingo')
    return datetime.now(tz).strftime('%m-%d-%Y')


def _parse_fanduel_page(html, sport):
    """
    Extrae predicciones de la página de FanDuel Research.
    Estructura típica: secciones por juego con 'numberFire Prediction'.
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n')

    games = []
    # Buscar bloques de juegos por patrón "Team A at Team B" + predicciones
    sections = re.split(r'###\s+|Game Info', text)

    pattern = re.compile(
        r'(?P<away>[A-Za-z\.\s]+?)\s+at\s+(?P<home>[A-Za-z\.\s]+?)(?:\s+Odds|\s*\n)'
        r'.*?'
        r'(?:numberFire Predicted Favorite[:\s]+(?P<fav>[A-Za-z\.\s]+?)\n)?'
        r'.*?'
        r'(?P<team1>[A-Za-z\.\s]+?)\s+Win Probability[:\s]+(?P<prob1>[\d\.]+)%'
        r'.*?'
        r'(?P<team2>[A-Za-z\.\s]+?)\s+Win Probability[:\s]+(?P<prob2>[\d\.]+)%',
        re.DOTALL
    )

    for match in pattern.finditer(text):
        home = match.group('home').strip()
        away = match.group('away').strip()
        team1 = match.group('team1').strip()
        prob1 = float(match.group('prob1'))
        prob2 = float(match.group('prob2'))

        # team1 es el favorito según el orden de aparición
        if team1.lower() in home.lower() or home.lower() in team1.lower():
            home_prob = prob1
            away_prob = prob2
        else:
            home_prob = prob2
            away_prob = prob1

        games.append({
            'sport': sport,
            'home': home,
            'away': away,
            'home_prob_model': round(home_prob, 1),
            'away_prob_model': round(away_prob, 1),
            'source': 'numberFire',
        })

    return games


def get_fanduel_predictions(sport='mlb'):
    """
    Retorna predicciones de FanDuel/numberFire para hoy.
    sport: 'mlb' o 'nba'
    """
    today = _get_today_str()
    url = f"https://www.fanduel.com/research/{sport}-betting-odds-{today}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"  FanDuel {sport.upper()} respondió {response.status_code}")
            return []
        return _parse_fanduel_page(response.text, sport.upper())
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching FanDuel {sport.upper()}: {e}")
        return []


if __name__ == '__main__':
    print("\n=== Predicciones MLB (numberFire via FanDuel) ===\n")
    mlb_picks = get_fanduel_predictions('mlb')
    print(f"Juegos encontrados: {len(mlb_picks)}\n")
    for g in mlb_picks:
        fav = g['home'] if g['home_prob_model'] > g['away_prob_model'] else g['away']
        fav_prob = max(g['home_prob_model'], g['away_prob_model'])
        print(f"{g['away']} @ {g['home']}")
        print(f"  Favorito modelo: {fav} ({fav_prob}%)")
        print()

    print("\n=== Predicciones NBA (numberFire via FanDuel) ===\n")
    nba_picks = get_fanduel_predictions('nba')
    print(f"Juegos encontrados: {len(nba_picks)}\n")
    for g in nba_picks:
        fav = g['home'] if g['home_prob_model'] > g['away_prob_model'] else g['away']
        fav_prob = max(g['home_prob_model'], g['away_prob_model'])
        print(f"{g['away']} @ {g['home']}")
        print(f"  Favorito modelo: {fav} ({fav_prob}%)")
        print()