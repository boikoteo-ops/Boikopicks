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
    Estrategia: encontrar cada bloque de juego identificado por
    'numberFire Predicted Favorite' y extraer las dos win probabilities.
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n')

    # Limpiar líneas vacías y espacios excesivos
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    cleaned = '\n'.join(lines)

    games = []

    # Patrón principal: capturar bloque desde el matchup hasta las win probs
    # Estructura en FanDuel:
    #   <Away> at <Home> [Odds, Lines & Predictions]
    #   ...
    #   numberFire Predicted Favorite: <FavTeam>
    #   <Team1> Win Probability: <X>%
    #   <Team2> Win Probability: <Y>%

    pattern = re.compile(
        r'([A-Z][A-Za-z\.\s]+?)\s+at\s+([A-Z][A-Za-z\.\s]+?)\s*(?:Odds|\n)'
        r'[\s\S]{0,3000}?'
        r'numberFire Predicted Favorite[:\s]+([A-Za-z\.\s]+?)\n'
        r'([A-Za-z\.\s]+?)\s+Win Probability[:\s]+([\d\.]+)%\n'
        r'([A-Za-z\.\s]+?)\s+Win Probability[:\s]+([\d\.]+)%',
        re.MULTILINE
    )

    for match in pattern.finditer(cleaned):
        away_raw = match.group(1).strip()
        home_raw = match.group(2).strip()
        fav_team = match.group(3).strip()
        team1 = match.group(4).strip()
        prob1 = float(match.group(5))
        team2 = match.group(6).strip()
        prob2 = float(match.group(7))

        # Determinar qué probabilidad va con home y cuál con away
        # comparando team1/team2 contra home/away
        home_prob = None
        away_prob = None

        if _name_matches(team1, home_raw):
            home_prob = prob1
            away_prob = prob2
        elif _name_matches(team1, away_raw):
            away_prob = prob1
            home_prob = prob2
        elif _name_matches(team2, home_raw):
            home_prob = prob2
            away_prob = prob1
        elif _name_matches(team2, away_raw):
            away_prob = prob2
            home_prob = prob1
        else:
            # Fallback: asumir orden home primero (FanDuel suele listar así)
            home_prob = prob1
            away_prob = prob2

        # Validación de sanity: deben sumar ~100%
        if abs((home_prob + away_prob) - 100) > 1:
            continue

        games.append({
            'sport': sport,
            'home': home_raw,
            'away': away_raw,
            'home_prob_model': round(home_prob, 1),
            'away_prob_model': round(away_prob, 1),
            'favorite': fav_team,
            'source': 'numberFire',
        })

    return games


def _name_matches(name_a, name_b):
    """
    Verifica si dos nombres de equipo refieren al mismo equipo.
    Compara palabras clave (último word usualmente es el nickname).
    """
    if not name_a or not name_b:
        return False
    a = name_a.lower().strip()
    b = name_b.lower().strip()
    if a == b:
        return True
    # Comparar la última palabra (nickname): "Los Angeles Dodgers" → "dodgers"
    a_last = a.split()[-1] if a.split() else ''
    b_last = b.split()[-1] if b.split() else ''
    if a_last and b_last and a_last == b_last:
        return True
    # Contención mutua para nombres cortos vs largos
    if a in b or b in a:
        return True
    return False


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
        print(f"{g['away']} ({g['away_prob_model']}%) @ {g['home']} ({g['home_prob_model']}%)")
        print(f"  Favorito modelo: {fav} ({fav_prob}%)")
        print()

    print("\n=== Predicciones NBA (numberFire via FanDuel) ===\n")
    nba_picks = get_fanduel_predictions('nba')
    print(f"Juegos encontrados: {len(nba_picks)}\n")
    for g in nba_picks:
        fav = g['home'] if g['home_prob_model'] > g['away_prob_model'] else g['away']
        fav_prob = max(g['home_prob_model'], g['away_prob_model'])
        print(f"{g['away']} ({g['away_prob_model']}%) @ {g['home']} ({g['home_prob_model']}%)")
        print(f"  Favorito modelo: {fav} ({fav_prob}%)")
        print()