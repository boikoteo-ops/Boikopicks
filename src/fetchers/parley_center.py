"""
Parley Center MLB fetcher.

Source: https://parleycenter.com/mlb.php

Devuelve dos funciones de entrada al engine:
  - get_parley_center_predictions(sport='mlb') -> lista ML
  - get_parley_center_totals(sport='mlb')      -> lista O/U

Formato ML:
    {
      "home": "Chicago Cubs",
      "away": "Houston Astros",
      "home_prob_parley": 57.0,
      "away_prob_parley": 43.0,
      "home_odds_parley": -145,
      "away_odds_parley": 120,
      "text_pick_team": "Chicago Cubs",
      "text_pick_type": "ML",       # 'ML' | 'RL' | None
    }

Formato O/U:
    {
      "home": "Chicago Cubs",
      "away": "Houston Astros",
      "ou_pick": "over",            # 'over' | 'under'
      "ou_line": 7.0,
      "ou_pct_over": 59,
      "ou_pct_under": 41,
      "text_pick_type": None,        # 'OU_OVER' | 'OU_UNDER' | None
    }
"""

import re
import requests
from bs4 import BeautifulSoup

URL = "https://parleycenter.com/mlb.php"
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
}

TEAM_NAME_MAP = {
    "ARIZONA DIAMONDBACKS": "Arizona Diamondbacks",
    "ATLANTA BRAVES": "Atlanta Braves",
    "BALTIMORE ORIOLES": "Baltimore Orioles",
    "BOSTON RED SOX": "Boston Red Sox",
    "CHICAGO CUBS": "Chicago Cubs",
    "CHICAGO WHITE SOX": "Chicago White Sox",
    "CINCINNATI REDS": "Cincinnati Reds",
    "CLEVELAND GUARDIANS": "Cleveland Guardians",
    "COLORADO ROCKIES": "Colorado Rockies",
    "DETROIT TIGERS": "Detroit Tigers",
    "HOUSTON ASTROS": "Houston Astros",
    "KANSAS CITY ROYALS": "Kansas City Royals",
    "LOS ANGELES ANGELS": "Los Angeles Angels",
    "LOS ANGELES DODGERS": "Los Angeles Dodgers",
    "MIAMI MARLINS": "Miami Marlins",
    "MILWAUKEE BREWERS": "Milwaukee Brewers",
    "MINNESOTA TWINS": "Minnesota Twins",
    "NEW YORK METS": "New York Mets",
    "NEW YORK YANKEES": "New York Yankees",
    "ATHLETICS": "Athletics",
    "OAKLAND ATHLETICS": "Athletics",
    "PHILADELPHIA PHILLIES": "Philadelphia Phillies",
    "PITTSBURGH PIRATES": "Pittsburgh Pirates",
    "SAN DIEGO PADRES": "San Diego Padres",
    "SAN FRANCISCO GIANTS": "San Francisco Giants",
    "SEATTLE MARINERS": "Seattle Mariners",
    "ST. LOUIS CARDINALS": "St. Louis Cardinals",
    "TAMPA BAY RAYS": "Tampa Bay Rays",
    "TEXAS RANGERS": "Texas Rangers",
    "TORONTO BLUE JAYS": "Toronto Blue Jays",
    "WASHINGTON NATIONALS": "Washington Nationals",
}


def _normalize_team(raw_name):
    if not raw_name:
        return None
    key = raw_name.strip().upper()
    return TEAM_NAME_MAP.get(key, raw_name.strip().title())


def _extract_text_pick(description_text, home_team, away_team):
    if not description_text:
        return {"team": None, "pick_type": None}

    text_up = description_text.upper()

    if re.search(r"\bBAJA\b\.?\s*$", text_up.strip()):
        return {"team": None, "pick_type": "OU_UNDER"}
    if re.search(r"\bALTA\b\.?\s*$", text_up.strip()):
        return {"team": None, "pick_type": "OU_OVER"}

    home_up = (home_team or "").upper()
    away_up = (away_team or "").upper()

    if "MONEY LINE" in text_up:
        ml_idx = text_up.rfind("MONEY LINE")
        home_idx = text_up.rfind(home_up, 0, ml_idx + 1) if home_up else -1
        away_idx = text_up.rfind(away_up, 0, ml_idx + 1) if away_up else -1
        if home_idx > away_idx and home_idx > -1:
            return {"team": home_team, "pick_type": "ML"}
        elif away_idx > -1:
            return {"team": away_team, "pick_type": "ML"}

    if "RUN LINE" in text_up:
        ml_idx = text_up.rfind("RUN LINE")
        home_idx = text_up.rfind(home_up, 0, ml_idx + 1) if home_up else -1
        away_idx = text_up.rfind(away_up, 0, ml_idx + 1) if away_up else -1
        if home_idx > away_idx and home_idx > -1:
            return {"team": home_team, "pick_type": "RL"}
        elif away_idx > -1:
            return {"team": away_team, "pick_type": "RL"}

    return {"team": None, "pick_type": None}


# Cache de un fetch por proceso (evita pegarle 2 veces al sitio si llamas ambas funciones)
_CACHED_GAMES = None
_CACHED = False


def _fetch_html():
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        print(f"   Parley Center HTTP status: {resp.status_code}")
        print(f"   Parley Center bytes: {len(resp.text)}")
        resp.raise_for_status()
        # Sanity check: ¿el HTML contiene el marcador esperado?
        if "PROBABILIDADES" in resp.text.upper():
            print(f"   Parley Center: marcador PROBABILIDADES encontrado en HTML")
        else:
            print(f"   Parley Center: marcador PROBABILIDADES NO encontrado en HTML")
            # Imprimir primeros 500 chars para inspeccionar
            print(f"   Parley Center sample: {resp.text[:500]}")
        return resp.text
    except Exception as e:
        print(f"   Parley Center fetch error: {e}")
        return None


def _parse_game_block(prob_h):
    teams_found = []
    el = prob_h
    while el and len(teams_found) < 2:
        el = el.find_previous(["h3"])
        if el is None:
            break
        raw_name = el.get_text(strip=True)
        if raw_name and raw_name.upper() == raw_name and len(raw_name) > 2:
            teams_found.insert(0, (el, raw_name))

    if len(teams_found) < 2:
        return None

    home_raw = teams_found[0][1]
    away_raw = teams_found[1][1]
    home_team = _normalize_team(home_raw)
    away_team = _normalize_team(away_raw)

    odds_data = {}
    for h3_el, raw_name in teams_found:
        block_text_parts = []
        sibling = h3_el.find_next_sibling()
        while sibling and sibling.name not in ("h3", "h5"):
            block_text_parts.append(sibling.get_text(" ", strip=True))
            sibling = sibling.find_next_sibling()
        block_text = " ".join(block_text_parts)

        money_m = re.search(r"MONEY:\s*(-?\+?\d+)", block_text, re.I)
        ou_m = re.search(r"ALTA/BAJA:\s*(\d+(?:\.\d+)?)", block_text, re.I)

        odds_data[raw_name] = {
            "money": int(money_m.group(1).replace("+", "")) if money_m else None,
            "ou_line": float(ou_m.group(1)) if ou_m else None,
        }

    ml_home_odds = odds_data[home_raw]["money"]
    ml_away_odds = odds_data[away_raw]["money"]
    ou_line = (
        odds_data[home_raw]["ou_line"]
        if odds_data[home_raw]["ou_line"] is not None
        else odds_data[away_raw]["ou_line"]
    )

    ml_home_pct = ml_away_pct = None
    ou_over_pct = ou_under_pct = None

    section = None
    pct_buffer = []
    description_paragraphs = []

    sibling = prob_h.find_next_sibling()
    while sibling:
        if sibling.name == "h3":
            break

        if sibling.name == "h5":
            heading = sibling.get_text(strip=True).upper()
            if "MONEY LINE" in heading:
                section = "ML"
            elif "ALTA/BAJA" in heading:
                section = "OU"
            else:
                section = None
            pct_buffer = []
            sibling = sibling.find_next_sibling()
            continue

        text = sibling.get_text(" ", strip=True)

        if section:
            pcts = re.findall(r"(\d+)\s*%", text)
            for p in pcts:
                pct_buffer.append(int(p))
                if len(pct_buffer) == 2:
                    if section == "ML":
                        ml_home_pct, ml_away_pct = pct_buffer
                    elif section == "OU":
                        ou_over_pct, ou_under_pct = pct_buffer
                    section = None
                    pct_buffer = []

        if sibling.name == "p" and text:
            description_paragraphs.append(text)

        sibling = sibling.find_next_sibling()

    full_description = " ".join(description_paragraphs)
    text_pick = _extract_text_pick(full_description, home_team, away_team)

    return {
        "home": home_team,
        "away": away_team,
        "ml_home_odds": ml_home_odds,
        "ml_away_odds": ml_away_odds,
        "ml_home_pct": ml_home_pct,
        "ml_away_pct": ml_away_pct,
        "ou_line": ou_line,
        "ou_over_pct": ou_over_pct,
        "ou_under_pct": ou_under_pct,
        "text_pick_team": text_pick["team"],
        "text_pick_type": text_pick["pick_type"],
    }


def _get_games_cached():
    """Obtiene la lista de juegos (cached para evitar duplicar fetch)."""
    global _CACHED_GAMES, _CACHED
    if _CACHED:
        return _CACHED_GAMES

    html = _fetch_html()
    games = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        prob_headers = [
            h for h in soup.find_all("h5")
            if "PROBABILIDADES" in h.get_text(strip=True).upper()
        ]
        print(f"   Parley Center: {len(prob_headers)} bloques PROBABILIDADES encontrados")
        if not prob_headers:
            print("   Parley Center: no se encontraron bloques PROBABILIDADES")
        for prob_h in prob_headers:
            try:
                game = _parse_game_block(prob_h)
                if game and game.get("home") and game.get("away"):
                    games.append(game)
            except Exception as e:
                print(f"   Parley Center parse error: {e}")
                continue

    _CACHED_GAMES = games
    _CACHED = True
    return games


def get_parley_center_predictions(sport='mlb'):
    """
    Predicciones ML de Parley Center.

    Returns: lista de dicts compatibles con merge_game_data.
    """
    if sport != 'mlb':
        return []

    games = _get_games_cached()
    predictions = []
    for g in games:
        if g["ml_home_pct"] is None or g["ml_away_pct"] is None:
            continue
        predictions.append({
            "home": g["home"],
            "away": g["away"],
            "home_prob_parley": float(g["ml_home_pct"]),
            "away_prob_parley": float(g["ml_away_pct"]),
            "home_odds_parley": g["ml_home_odds"],
            "away_odds_parley": g["ml_away_odds"],
            "text_pick_team": g["text_pick_team"],
            "text_pick_type": g["text_pick_type"],
        })
    return predictions


def get_parley_center_totals(sport='mlb'):
    """
    Predicciones O/U de Parley Center.

    Returns: lista de dicts compatibles con merge_ou_data.
    """
    if sport != 'mlb':
        return []

    games = _get_games_cached()
    totals = []
    for g in games:
        if g["ou_over_pct"] is None or g["ou_under_pct"] is None or g["ou_line"] is None:
            continue

        if g["ou_over_pct"] >= g["ou_under_pct"]:
            ou_pick = "over"
        else:
            ou_pick = "under"

        totals.append({
            "home": g["home"],
            "away": g["away"],
            "ou_pick": ou_pick,
            "ou_line": g["ou_line"],
            "ou_pct_over": g["ou_over_pct"],
            "ou_pct_under": g["ou_under_pct"],
            "text_pick_type": g["text_pick_type"],
        })
    return totals


if __name__ == "__main__":
    print("=== Parley Center fetcher test ===")
    ml = get_parley_center_predictions('mlb')
    print(f"\nML predictions: {len(ml)} juegos")
    for p in ml[:3]:
        print(f"  {p['away']} @ {p['home']}: {p['home_prob_parley']}%/{p['away_prob_parley']}%  "
              f"odds {p['home_odds_parley']}/{p['away_odds_parley']}  "
              f"text_pick={p['text_pick_team']} ({p['text_pick_type']})")

    ou = get_parley_center_totals('mlb')
    print(f"\nO/U predictions: {len(ou)} juegos")
    for p in ou[:3]:
        print(f"  {p['away']} @ {p['home']}: {p['ou_pick'].upper()} {p['ou_line']} "
              f"({p['ou_pct_over']}%/{p['ou_pct_under']}%)  text={p['text_pick_type']}")
