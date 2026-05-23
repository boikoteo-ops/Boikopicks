"""
Parley Center MLB fetcher.

Source: https://parleycenter.com/mlb.php

Estrategia de parsing v2:
La estructura HTML usa <div> en lugar de h3/h5. Cada juego es un div con TODO
el bloque concatenado:
"PROBABILIDADES <home> <away> MONEY LINE 53% 1 1 47% RUN LINE ... ALTA/BAJA (X.X) ..%  .."

Estrategia: encontrar divs que contengan "PROBABILIDADES" + "MONEY LINE" + "ALTA/BAJA",
y aplicar regex para extraer los datos.
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

# Lista de todos los equipos MLB (en mayusculas como aparecen en Parley)
# El orden importa para el matching: los nombres mas largos primero
# para evitar que "ATHLETICS" matchee dentro de "OAKLAND ATHLETICS"
MLB_TEAMS_RAW = [
    "ARIZONA DIAMONDBACKS",
    "ATLANTA BRAVES",
    "BALTIMORE ORIOLES",
    "BOSTON RED SOX",
    "CHICAGO WHITE SOX",
    "CHICAGO CUBS",
    "CINCINNATI REDS",
    "CLEVELAND GUARDIANS",
    "COLORADO ROCKIES",
    "DETROIT TIGERS",
    "HOUSTON ASTROS",
    "KANSAS CITY ROYALS",
    "LOS ANGELES ANGELS",
    "LOS ANGELES DODGERS",
    "MIAMI MARLINS",
    "MILWAUKEE BREWERS",
    "MINNESOTA TWINS",
    "NEW YORK METS",
    "NEW YORK YANKEES",
    "OAKLAND ATHLETICS",
    "ATHLETICS",
    "PHILADELPHIA PHILLIES",
    "PITTSBURGH PIRATES",
    "SAN DIEGO PADRES",
    "SAN FRANCISCO GIANTS",
    "SEATTLE MARINERS",
    "ST. LOUIS CARDINALS",
    "TAMPA BAY RAYS",
    "TEXAS RANGERS",
    "TORONTO BLUE JAYS",
    "WASHINGTON NATIONALS",
]

# Mapeo a formato ingles estandar
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


def _fetch_html():
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"   Parley Center fetch error: {e}")
        return None


def _extract_text_pick_type(block_text_upper):
    """
    Extrae el pick textual del final del bloque.
    Patrones tipicos al final del bloque (en MAYUSCULAS, despues de los %):
      "... CHICAGO CUBS MONEY LINE"
      "... MIAMI MARLINS RUN LINE"
      "... BAJA"
      "... ALTA"
    """
    if not block_text_upper:
        return {"team_raw": None, "pick_type": None}

    # Tail = ultimos 200 chars donde estaria el pick en bold
    tail = block_text_upper[-300:].strip()

    # Standalone BAJA/ALTA al final (despues de la ultima palabra)
    if re.search(r"\bBAJA\b\.?\s*$", tail):
        return {"team_raw": None, "pick_type": "OU_UNDER"}
    if re.search(r"\bALTA\b\.?\s*$", tail):
        return {"team_raw": None, "pick_type": "OU_OVER"}

    # Buscar "TEAM MONEY LINE" o "TEAM RUN LINE" en el tail
    # Probamos cada equipo de la lista (longest first para evitar conflictos)
    sorted_teams = sorted(MLB_TEAMS_RAW, key=len, reverse=True)

    for pick_type, pattern_word in [("ML", "MONEY LINE"), ("RL", "RUN LINE")]:
        if pattern_word in tail:
            ml_idx = tail.rfind(pattern_word)
            # Buscar nombre de equipo justo antes
            tail_before_ml = tail[:ml_idx].rstrip()
            for team in sorted_teams:
                # Verificar si el tail termina con este nombre justo antes de "MONEY LINE"
                if tail_before_ml.endswith(team):
                    return {"team_raw": team, "pick_type": pick_type}
            # Fallback: encontrar el equipo mas reciente antes de "MONEY LINE"
            for team in sorted_teams:
                idx_team = tail_before_ml.rfind(team)
                if idx_team >= 0:
                    return {"team_raw": team, "pick_type": pick_type}

    return {"team_raw": None, "pick_type": None}


def _parse_block(block_text):
    """
    Parsea un bloque de texto plano de un juego completo de Parley Center.

    Estructura esperada del texto (despues de strip de imagenes/whitespace extra):
      "<HOME> HORA: HH:MM (-4 GMT) MONEY: -145 (1,69) ALTA/BAJA: 7.0 RECORD ... PREDICCION: 8
       <AWAY> MONEY: 120 (2,20) RUNLINE: 1.5 RECORD ... PREDICCION: 5
       PROBABILIDADES <HOME> <AWAY>
       MONEY LINE 57% 1 1 43%
       RUN LINE 54% 1 1 46%
       ALTA/BAJA (7.0) 59% 1 1 41%
       [descripcion...] <PICK_TEAM> MONEY LINE."
    """
    text_up = block_text.upper()

    # Detectar los 2 equipos: aparecen en orden HOME, AWAY al inicio
    # Estrategia: encontrar los primeros 2 nombres de equipos MLB en el texto
    sorted_teams = sorted(MLB_TEAMS_RAW, key=len, reverse=True)
    teams_found_with_pos = []  # (team, position)
    seen_teams = set()

    for team in sorted_teams:
        # findall all occurrences positions
        start = 0
        while True:
            idx = text_up.find(team, start)
            if idx < 0:
                break
            # Verificar boundaries: no debe ser parte de otro nombre mas largo
            # (esto ya lo evitamos al buscar longest first y trackeando seen)
            # Verificar que no este dentro de un team ya capturado
            already_captured = any(
                seen_idx <= idx < seen_idx + len(seen_team)
                or idx <= seen_idx < idx + len(team)
                for seen_team, seen_idx in seen_teams
            )
            if not already_captured:
                teams_found_with_pos.append((team, idx))
                seen_teams.add((team, idx))
            start = idx + len(team)

    if len(teams_found_with_pos) < 2:
        return None

    # Ordenar por posicion en el texto (primero el que aparece antes)
    teams_found_with_pos.sort(key=lambda x: x[1])

    # Los primeros 2 son home y away (en ese orden segun aparecen)
    home_raw = teams_found_with_pos[0][0]
    away_raw = teams_found_with_pos[1][0]
    home_team = _normalize_team(home_raw)
    away_team = _normalize_team(away_raw)

    # === Extraer MONEY de cada equipo ===
    # El primer MONEY tras el home, el segundo MONEY tras el away
    money_matches = list(re.finditer(r"MONEY:\s*(-?\+?\d+)", text_up))
    ml_home_odds = ml_away_odds = None
    if len(money_matches) >= 2:
        try:
            ml_home_odds = int(money_matches[0].group(1).replace("+", ""))
            ml_away_odds = int(money_matches[1].group(1).replace("+", ""))
        except ValueError:
            pass

    # === Extraer ALTA/BAJA line ===
    ou_line_m = re.search(r"ALTA/BAJA:\s*(\d+(?:\.\d+)?)", text_up)
    ou_line = float(ou_line_m.group(1)) if ou_line_m else None

    # === Extraer % MONEY LINE (los dos primeros %) ===
    # El bloque MONEY LINE tiene "MONEY LINE 57% 1 1 43%"
    ml_pct_m = re.search(
        r"MONEY\s+LINE\s+(\d+)\s*%[^%]*?(\d+)\s*%",
        text_up, re.DOTALL
    )
    ml_home_pct = ml_away_pct = None
    if ml_pct_m:
        try:
            ml_home_pct = int(ml_pct_m.group(1))
            ml_away_pct = int(ml_pct_m.group(2))
        except ValueError:
            pass

    # === Extraer % ALTA/BAJA ===
    # Bloque "ALTA/BAJA (7.0) 59% 1 1 41%"
    ou_pct_m = re.search(
        r"ALTA/BAJA\s*\(\d+(?:\.\d+)?\)\s+(\d+)\s*%[^%]*?(\d+)\s*%",
        text_up, re.DOTALL
    )
    ou_over_pct = ou_under_pct = None
    if ou_pct_m:
        try:
            ou_over_pct = int(ou_pct_m.group(1))
            ou_under_pct = int(ou_pct_m.group(2))
        except ValueError:
            pass

    # === Pick textual ===
    text_pick = _extract_text_pick_type(text_up)
    text_pick_team = _normalize_team(text_pick["team_raw"]) if text_pick["team_raw"] else None

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
        "text_pick_team": text_pick_team,
        "text_pick_type": text_pick["pick_type"],
    }


# Cache simple para no fetchar 2 veces (ML y O/U comparten data)
_CACHED_GAMES = None
_CACHED = False


def _get_games_cached():
    global _CACHED_GAMES, _CACHED
    if _CACHED:
        return _CACHED_GAMES

    html = _fetch_html()
    games = []
    if html:
        soup = BeautifulSoup(html, "html.parser")
        # Buscar TODOS los elementos (cualquier tag) que contengan "PROBABILIDADES"
        # como string directo. Filtrar para quedarnos con el mas pequeno (mas atomico)
        # que contiene todo el bloque de un juego.

        # Estrategia: encontrar elementos con texto que contenga TODOS los marcadores
        # de un juego completo: PROBABILIDADES, MONEY LINE, ALTA/BAJA
        candidate_blocks = []
        for el in soup.find_all(True):  # todos los tags
            text = el.get_text(" ", strip=True)
            text_up = text.upper()
            # Debe contener los 3 marcadores
            if ("PROBABILIDADES" in text_up
                    and "MONEY LINE" in text_up
                    and "ALTA/BAJA" in text_up):
                # Y debe tener un MONEY: explicito (es un bloque de juego, no el contenedor entero)
                if "MONEY:" in text_up:
                    candidate_blocks.append((el, len(text)))

        # Ordenar por tamano de texto: bloques mas pequenos primero (mas atomicos)
        candidate_blocks.sort(key=lambda x: x[1])

        # Quedarnos solo con los bloques minimos (no contenedores grandes que abarcan multiples juegos)
        # Un bloque de un juego tipico tiene 500-1500 caracteres
        selected = []
        used_text_hashes = set()
        for el, text_len in candidate_blocks:
            text = el.get_text(" ", strip=True)
            # Skip duplicados (mismo texto exacto)
            text_hash = hash(text[:300])
            if text_hash in used_text_hashes:
                continue
            # Skip bloques gigantes que abarcan multiples juegos (>3000 chars normalmente significa que abarca >=2)
            if text_len > 4000:
                continue
            # Verificar que NO contiene multiples bloques PROBABILIDADES
            num_prob = text.upper().count("PROBABILIDADES")
            if num_prob > 1:
                continue
            used_text_hashes.add(text_hash)
            selected.append(el)

        print(f"   Parley Center: {len(selected)} bloques de juego seleccionados (de {len(candidate_blocks)} candidatos)")

        for el in selected:
            text = el.get_text(" ", strip=True)
            try:
                game = _parse_block(text)
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
