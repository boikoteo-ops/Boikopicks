"""
Obtiene predicciones de numberFire + odds reales del FanDuel Sportsbook
desde fanduel.com/research/{sport}-betting-odds-{date}.

Mejora vs version anterior:
- Antes solo capturaba 'home_prob_model' / 'away_prob_model' (modelo numberFire)
- Ahora tambien captura 'home_odds_real' / 'away_odds_real' (odds reales del sportsbook)

Esto permite al engine calcular ROI con precision real en vez de estimacion.
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


def _name_matches(name_a, name_b):
    """Verifica si dos nombres de equipo refieren al mismo equipo."""
    if not name_a or not name_b:
        return False
    a = name_a.lower().strip()
    b = name_b.lower().strip()
    if a == b:
        return True
    a_last = a.split()[-1] if a.split() else ''
    b_last = b.split()[-1] if b.split() else ''
    if a_last and b_last and a_last == b_last:
        return True
    if a in b or b in a:
        return True
    return False


def _extract_text_from_article(html):
    """
    FanDuel Research usa Next.js con un JSON embebido que contiene
    el contenido del articulo en bloques de Sanity CMS.
    Esta funcion extrae el texto plano del articulo.

    Returns:
        str del texto plano, o '' si no se pudo extraer.
    """
    import json

    # 1. Buscar __NEXT_DATA__
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>',
                       html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            article = data.get('props', {}).get('pageProps', {}).get('article', {})
            body_str = article.get('body', '')
            if body_str:
                blocks = json.loads(body_str) if isinstance(body_str, str) else body_str
                if isinstance(blocks, list):
                    texts = []
                    for block in blocks:
                        if isinstance(block, dict) and block.get('_type') == 'block':
                            children = block.get('children', [])
                            line = ''.join(
                                c.get('text', '') for c in children
                                if isinstance(c, dict)
                            )
                            if line:
                                texts.append(line)
                    if texts:
                        return '\n'.join(texts)
        except (ValueError, KeyError, TypeError):
            pass

    # 2. Fallback: extraer texto de HTML completo via BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return '\n'.join(lines)


def _build_odds_map(text):
    """
    Construye mapping de team nickname -> american odds capturado.
    Patron: '<TeamNickname> Moneyline Odds: -152' o '+128'

    Returns:
        dict tipo {'phillies': -152, 'reds': 128, 'rays': -120, ...}
    """
    pattern = re.compile(
        r'([A-Z][A-Za-z\.\s]+?)\s+Moneyline Odds[:\s]+([+-]\d+)'
    )
    odds_map = {}
    for match in pattern.finditer(text):
        team_text = match.group(1).strip()
        odds = int(match.group(2))
        # Indexar por la ultima palabra (nickname): 'White Sox' -> 'sox'
        team_lower = team_text.lower()
        odds_map[team_lower] = odds
        last_word = team_lower.split()[-1] if team_lower.split() else ''
        if last_word and last_word != team_lower:
            odds_map[last_word] = odds
    return odds_map


def _find_odds_for_team(team_name, odds_map):
    """
    Busca las odds reales para un equipo dado, usando matching flexible.
    """
    if not team_name or not odds_map:
        return None
    team_lower = team_name.lower().strip()

    # Match exacto
    if team_lower in odds_map:
        return odds_map[team_lower]

    # Match por ultima palabra (nickname)
    last = team_lower.split()[-1] if team_lower.split() else ''
    if last and last in odds_map:
        return odds_map[last]

    # Match parcial: alguna clave esta contenida en team_name o viceversa
    for key, odds in odds_map.items():
        if _name_matches(key, team_name):
            return odds

    return None


def _parse_fanduel_page(html, sport):
    """
    Extrae predicciones + odds reales de la pagina de FanDuel Research.
    """
    text = _extract_text_from_article(html)

    # Construir mapa de odds reales del sportsbook
    odds_map = _build_odds_map(text)

    games = []

    # Patron principal (igual que antes pero usando texto del article):
    pattern = re.compile(
        r'([A-Z][A-Za-z\.\s]+?)\s+at\s+([A-Z][A-Za-z\.\s]+?)\s*Odds'
        r'[\s\S]{0,3000}?'
        r'numberFire Predicted Favorite[:\s]+([A-Za-z\.\s]+?)\n'
        r'([A-Za-z\.\s]+?)\s+Win Probability[:\s]+([\d\.]+)%\n'
        r'([A-Za-z\.\s]+?)\s+Win Probability[:\s]+([\d\.]+)%',
        re.MULTILINE
    )

    for match in pattern.finditer(text):
        away_raw = match.group(1).strip()
        home_raw = match.group(2).strip()

        # El primer match suele incluir el titulo de seccion antes del nombre real
        # (ej "MLB Odds and Predictions\nCincinnati Reds"). Tomamos solo la
        # ultima linea, que es siempre el nombre del equipo.
        if '\n' in away_raw:
            away_raw = away_raw.split('\n')[-1].strip()
        if '\n' in home_raw:
            home_raw = home_raw.split('\n')[-1].strip()
        fav_team = match.group(3).strip()
        team1 = match.group(4).strip()
        prob1 = float(match.group(5))
        team2 = match.group(6).strip()
        prob2 = float(match.group(7))

        # Asignar probs a home/away
        home_prob = None
        away_prob = None
        if _name_matches(team1, home_raw):
            home_prob, away_prob = prob1, prob2
        elif _name_matches(team1, away_raw):
            away_prob, home_prob = prob1, prob2
        elif _name_matches(team2, home_raw):
            home_prob, away_prob = prob2, prob1
        elif _name_matches(team2, away_raw):
            away_prob, home_prob = prob2, prob1
        else:
            home_prob, away_prob = prob1, prob2

        if abs((home_prob + away_prob) - 100) > 1:
            continue

        # === NUEVO: capturar odds reales del sportsbook ===
        home_odds_real = _find_odds_for_team(home_raw, odds_map)
        away_odds_real = _find_odds_for_team(away_raw, odds_map)

        games.append({
            'sport': sport,
            'home': home_raw,
            'away': away_raw,
            'home_prob_model': round(home_prob, 1),
            'away_prob_model': round(away_prob, 1),
            'home_odds_real': home_odds_real,   # NUEVO
            'away_odds_real': away_odds_real,   # NUEVO
            'favorite': fav_team,
            'source': 'numberFire',
        })

    return games


def get_fanduel_predictions(sport='mlb'):
    """
    Retorna predicciones numberFire + odds reales del FanDuel Sportsbook.
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
    print("\n=== Predicciones MLB (numberFire + odds reales) ===\n")
    mlb_picks = get_fanduel_predictions('mlb')
    print(f"Juegos encontrados: {len(mlb_picks)}\n")
    for g in mlb_picks:
        fav = g['home'] if g['home_prob_model'] > g['away_prob_model'] else g['away']
        fav_prob = max(g['home_prob_model'], g['away_prob_model'])
        print(f"{g['away']:<25} ({g['away_prob_model']:>4}%) @ {g['home']:<25} ({g['home_prob_model']:>4}%)")
        print(f"  Odds reales: away={g['away_odds_real']} | home={g['home_odds_real']}")
        print()
