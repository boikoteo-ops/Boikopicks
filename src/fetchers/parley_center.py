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

    ANCHOR principal: el patrón "PROBABILIDADES <HOME> <AWAY>" identifica los 2 equipos
    correctos del juego, sin importar qué equipos aparezcan antes en el texto (datos del juego anterior).

    Estructura esperada despues del anchor PROBABILIDADES:
       "PROBABILIDADES <HOME> <AWAY>
        MONEY LINE 57% 1 1 43%
        ...
        ALTA/BAJA (7.0) 59% 1 1 41%
        [descripcion...] <PICK_TEAM> MONEY LINE."

    Datos de odds (MONEY:) estan ANTES de PROBABILIDADES; usamos posicionamiento.
    """
    text_up = block_text.upper()

    # === ANCHOR: encontrar PROBABILIDADES y los 2 equipos que le siguen ===
    prob_idx = text_up.find("PROBABILIDADES")
    if prob_idx < 0:
        return None

    # Tomar los siguientes 200 chars despues de PROBABILIDADES — alli estan home y away
    after_prob = text_up[prob_idx + len("PROBABILIDADES"):prob_idx + len("PROBABILIDADES") + 200]

    # Buscar los 2 nombres de equipo (longest first para evitar conflictos)
    sorted_teams = sorted(MLB_TEAMS_RAW, key=len, reverse=True)
    teams_after_prob = []  # [(team_raw, position_in_after_prob)]
    seen_ranges = []  # [(start, end)] ya capturados

    for team in sorted_teams:
        # Encontrar TODAS las ocurrencias en after_prob
        start = 0
        while True:
            idx = after_prob.find(team, start)
            if idx < 0:
                break
            # Verificar que no este dentro de un rango ya capturado
            overlaps = any(s <= idx < e or idx <= s < idx + len(team)
                           for s, e in seen_ranges)
            if not overlaps:
                teams_after_prob.append((team, idx))
                seen_ranges.append((idx, idx + len(team)))
            start = idx + len(team)

    if len(teams_after_prob) < 2:
        return None

    # Tomar los 2 que aparecen mas temprano en after_prob
    teams_after_prob.sort(key=lambda x: x[1])
    home_raw = teams_after_prob[0][0]
    away_raw = teams_after_prob[1][0]
    home_team = _normalize_team(home_raw)
    away_team = _normalize_team(away_raw)

    # === Extraer MONEY de cada equipo (estan ANTES de PROBABILIDADES) ===
    # Tomar todos los MONEY: que aparezcan ANTES de prob_idx en orden:
    # el primero es home, el segundo es away
    text_before_prob = text_up[:prob_idx]
    money_matches = list(re.finditer(r"MONEY:\s*(-?\+?\d+)", text_before_prob))
    ml_home_odds = ml_away_odds = None
    if len(money_matches) >= 2:
        try:
            # Los 2 ULTIMOS MONEY: antes de PROBABILIDADES son los de este juego
            ml_home_odds = int(money_matches[-2].group(1).replace("+", ""))
            ml_away_odds = int(money_matches[-1].group(1).replace("+", ""))
        except ValueError:
            pass

    # === Extraer ALTA/BAJA line (ultima ALTA/BAJA: antes de PROBABILIDADES) ===
    ou_line = None
    ou_line_matches = list(re.finditer(r"ALTA/BAJA:\s*(\d+(?:\.\d+)?)", text_before_prob))
    if ou_line_matches:
        try:
            ou_line = float(ou_line_matches[-1].group(1))
        except ValueError:
            pass

    # === Extraer % MONEY LINE (los dos primeros % despues de PROBABILIDADES) ===
    text_after_prob_full = text_up[prob_idx:]
    ml_pct_m = re.search(
        r"MONEY\s+LINE\s+(\d+)\s*%[^%]*?(\d+)\s*%",
        text_after_prob_full, re.DOTALL
    )
    ml_home_pct = ml_away_pct = None
    if ml_pct_m:
        try:
            ml_home_pct = int(ml_pct_m.group(1))
            ml_away_pct = int(ml_pct_m.group(2))
        except ValueError:
            pass

    # === Extraer % ALTA/BAJA ===
    ou_pct_m = re.search(
        r"ALTA/BAJA\s*\(\d+(?:\.\d+)?\)\s+(\d+)\s*%[^%]*?(\d+)\s*%",
        text_after_prob_full, re.DOTALL
    )
    ou_over_pct = ou_under_pct = None
    if ou_pct_m:
        try:
            ou_over_pct = int(ou_pct_m.group(1))
            ou_under_pct = int(ou_pct_m.group(2))
        except ValueError:
            pass

    # === Pick textual (al final del bloque) ===
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
        # Estrategia nueva: tomar TODO el texto de la pagina y dividirlo por "PROBABILIDADES"
        # Cada chunk despues del split contiene un juego completo:
        #   "<HOME> <AWAY> MONEY LINE 57% 43% RUN LINE ... ALTA/BAJA ... [texto] PICK."
        # Pero NO tiene el HOME y AWAY con MONEY: porque eso esta ANTES de "PROBABILIDADES"
        # Asi que cada chunk N contiene:
        #   - El final del juego N (el bloque PROBABILIDADES + descripcion + pick textual)
        #   - El inicio del juego N+1 (los nombres de equipos con MONEY:, RECORD, etc.)
        #
        # Por simplicidad: dividir tambien por marcadores que separen bien.
        # En la practica funciona mejor partir por "PROBABILIDADES" y reagrupar.

        full_text = soup.get_text(" ", strip=False)
        # Normalizar whitespace
        full_text = re.sub(r"\s+", " ", full_text)

        # Dividir por "PROBABILIDADES" — cada chunk[i] termina antes de su PROBABILIDADES,
        # y chunk[i+1] empieza despues.
        # Estructura real:
        #   ANTES_DE_PROB1: [home1 datos] [away1 datos]
        #   PROB1: [pcts de juego 1] [texto descripcion juego 1, termina con pick]
        #          [home2 datos] [away2 datos]
        #   PROB2: [pcts de juego 2] [texto descripcion 2]
        #          [home3 datos] [away3 datos]
        #   ...
        #
        # Asi que un BLOQUE DE JUEGO N completo es:
        #   chunks[N-1].split() final (donde estan home/away con MONEY:)
        #   + "PROBABILIDADES" + chunks[N] hasta donde aparece el siguiente home/away
        #
        # Solucion mas simple: para cada PROBABILIDADES, tomar una ventana de texto
        # que abarque desde ~1500 chars antes hasta el siguiente PROBABILIDADES (o fin).

        prob_positions = []
        for m in re.finditer(r"\bPROBABILIDADES\b", full_text, re.I):
            prob_positions.append(m.start())

        print(f"   Parley Center: {len(prob_positions)} marcadores PROBABILIDADES en texto plano")

        for i, prob_start in enumerate(prob_positions):
            # Inicio del bloque: 1500 chars antes (donde estan los nombres de equipos con MONEY:)
            block_start = max(0, prob_start - 1500)
            # Si hay un PROBABILIDADES anterior, no retroceder mas alla de el
            if i > 0:
                block_start = max(block_start, prob_positions[i - 1] + len("PROBABILIDADES"))
            # Fin del bloque: hasta el siguiente PROBABILIDADES o fin del texto
            if i + 1 < len(prob_positions):
                block_end = prob_positions[i + 1]
            else:
                block_end = len(full_text)

            block_text = full_text[block_start:block_end]

            try:
                game = _parse_block(block_text)
                if game and game.get("home") and game.get("away"):
                    games.append(game)
            except Exception as e:
                print(f"   Parley Center parse error: {e}")
                continue

        print(f"   Parley Center: {len(games)} juegos parseados exitosamente")

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
