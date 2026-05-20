"""
Verifica resultados de picks previos y actualiza el historial.
Corre cada noche para procesar los picks del dia anterior.

Soporta picks de:
- Money Line (bet_type='moneyline' o sin bet_type — legacy)
- Totales O/U (bet_type='total')
"""
import json
import os
from datetime import datetime, timedelta
import pytz

from src.fetchers.mlb_results import get_mlb_results, get_nba_results


HISTORY_FILE = 'output/history.json'


def _normalize_team(name):
    return name.lower().strip().replace('.', '') if name else ''


def _teams_match(name1, name2):
    n1 = _normalize_team(name1)
    n2 = _normalize_team(name2)
    if not n1 or not n2:
        return False
    return n1 == n2 or n1 in n2 or n2 in n1


def load_history():
    """Carga el historial existente."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'tracked_picks': [], 'last_update': None}


def save_history(history):
    """Guarda el historial."""
    os.makedirs('output', exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _find_game_result(pick, results):
    """Busca el resultado correspondiente a un pick por home/away."""
    for result in results:
        if (_teams_match(pick['home'], result['home']) and
            _teams_match(pick['away'], result['away'])):
            return result
    return None


def verify_pick_ml(pick, result):
    """
    Verifica un pick de Money Line.
    Retorna 'win' o 'loss'.
    """
    return 'win' if _teams_match(pick['pick'], result['winner']) else 'loss'


def verify_pick_ou(pick, result):
    """
    Verifica un pick Over/Under.
    Necesita: pick['side'] in ('over','under') y pick['line'] numerica.

    El total real se calcula sumando los scores del juego.
    Retorna 'win', 'loss' o 'push'.
    """
    # Calcular total real desde el resultado
    if result.get('sport') == 'NBA':
        total = result.get('total_points')
    else:
        total = result.get('total_runs')

    if total is None:
        # Fallback: sumar scores
        home_score = result.get('home_score', 0)
        away_score = result.get('away_score', 0)
        total = home_score + away_score

    line = pick.get('line')
    side = pick.get('side', '').lower()

    if line is None or side not in ('over', 'under'):
        return None  # No podemos verificar

    if total == line:
        return 'push'  # Empate: stake devuelto

    if side == 'over':
        return 'win' if total > line else 'loss'
    else:  # under
        return 'win' if total < line else 'loss'


def verify_pick(pick, results):
    """
    Dispatcher: verifica un pick segun su bet_type.
    Retorna 'win', 'loss', 'push' o None (sin resultado).
    """
    result = _find_game_result(pick, results)
    if not result:
        return None

    bet_type = pick.get('bet_type', 'moneyline')  # default a ML para legacy

    if bet_type == 'total':
        return verify_pick_ou(pick, result)
    else:
        return verify_pick_ml(pick, result)


def verify_picks_for_date(history, date_str):
    """
    Verifica los picks de una fecha especifica contra los resultados.
    Modifica history en memoria.
    """
    print(f"Obteniendo resultados de {date_str}...")
    mlb_results = get_mlb_results(date_str)
    nba_results = get_nba_results(date_str)
    all_results = mlb_results + nba_results
    print(f"  Juegos finalizados: {len(all_results)}")

    updated = 0
    for tracked in history['tracked_picks']:
        if tracked.get('date_played') != date_str:
            continue
        if tracked.get('result') is not None:
            continue

        result = verify_pick(tracked, all_results)
        if result is not None:
            tracked['result'] = result
            tracked['verified_at'] = datetime.now(
                pytz.timezone('America/Santo_Domingo')
            ).isoformat()
            updated += 1

    print(f"  Picks verificados: {updated}")
    return history


def add_todays_picks_to_tracking(history):
    """
    Lee picks.json actual y agrega los picks de hoy al historial.
    Modifica history en memoria.

    Soporta picks ML (bet_type='moneyline') y O/U (bet_type='total').
    Para O/U agrega tambien line y side (necesarios para verificar despues).
    """
    if not os.path.exists('output/picks.json'):
        print("No existe output/picks.json")
        return history

    with open('output/picks.json', 'r', encoding='utf-8') as f:
        picks_data = json.load(f)

    tz = pytz.timezone('America/Santo_Domingo')
    today_str = datetime.now(tz).strftime('%Y-%m-%d')

    # IDs unicos: incluye bet_type para que ML y O/U del mismo juego no colisionen
    # (ej. New York Yankees ML + Yankees-Blue Jays UNDER 7.5)
    def _pick_key(p):
        bet_type = p.get('bet_type', 'moneyline')
        if bet_type == 'total':
            return (p.get('date_played') or today_str, bet_type, p.get('home'),
                    p.get('away'), p.get('pick'), p.get('line'))
        else:
            return (p.get('date_played') or today_str, bet_type, p.get('home'),
                    p.get('away'), p.get('pick'))

    existing_ids = {_pick_key(p) for p in history['tracked_picks']}

    added = 0
    for pick in picks_data.get('picks', []):
        bet_type = pick.get('bet_type', 'moneyline')

        # Construir entry comun
        entry = {
            'date_played': today_str,
            'sport': pick['sport'],
            'bet_type': bet_type,
            'home': pick['home'],
            'away': pick['away'],
            'pick': pick['pick'],
            'tier': pick['tier'],
            'confidence': pick['confidence'],
            'sources_count': pick.get('sources_count'),
            'result': None,
            'verified_at': None,
            'tracked_at': datetime.now(tz).isoformat(),
        }

        if bet_type == 'total':
            # Campos especificos de O/U
            entry['side'] = pick.get('side')  # 'over' o 'under'
            entry['line'] = pick.get('line')
            entry['odds_american'] = pick.get('odds_american')
            entry['agree_count'] = pick.get('agree_count')
            entry['sources_unanimous'] = pick.get('sources_unanimous', False)
        else:
            # Campos especificos de ML
            entry['side'] = pick.get('side')  # 'home' o 'away'
            entry['model_prob'] = pick.get('model_prob')
            entry['edge'] = pick.get('edge')
            entry['estimated_odds'] = pick.get('estimated_odds')
            entry['sources_agree'] = pick.get('sources_agree')

        # Crear copia temporal con date_played asignado para el key
        entry_copy = dict(entry)
        key = _pick_key(entry_copy)
        if key in existing_ids:
            continue

        history['tracked_picks'].append(entry)
        added += 1

    print(f"  Nuevos picks rastreados: {added}")
    return history


def run_verification():
    """Pipeline completo de verificacion."""
    tz = pytz.timezone('America/Santo_Domingo')
    now = datetime.now(tz)

    print("=" * 60)
    print(f"VERIFICACION DE PICKS")
    print(f"Fecha: {now.strftime('%A %d/%m/%Y %I:%M %p')} AST")
    print("=" * 60)

    history = load_history()

    print("\n[1/3] Agregando picks de hoy al tracking...")
    history = add_todays_picks_to_tracking(history)

    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    print(f"\n[2/3] Verificando picks de {yesterday_str}...")
    history = verify_picks_for_date(history, yesterday_str)

    day_before = now - timedelta(days=2)
    day_before_str = day_before.strftime('%Y-%m-%d')
    print(f"\n[3/3] Verificando picks de {day_before_str} (catch-up)...")
    history = verify_picks_for_date(history, day_before_str)

    history['last_update'] = now.isoformat()
    save_history(history)

    # Resumen separado ML vs O/U
    total = len(history['tracked_picks'])
    ml_picks = [p for p in history['tracked_picks'] if p.get('bet_type', 'moneyline') == 'moneyline']
    ou_picks = [p for p in history['tracked_picks'] if p.get('bet_type') == 'total']

    def _summarize(picks, label):
        verified = [p for p in picks if p.get('result') in ('win', 'loss', 'push')]
        wins = sum(1 for p in verified if p.get('result') == 'win')
        losses = sum(1 for p in verified if p.get('result') == 'loss')
        pushes = sum(1 for p in verified if p.get('result') == 'push')
        pending = len(picks) - len(verified)
        wr_denom = wins + losses  # pushes no cuentan
        wr = (wins / wr_denom * 100) if wr_denom else 0
        print(f"\n  {label}: {len(picks)} totales, {len(verified)} verificados")
        if verified:
            push_str = f", {pushes}P" if pushes else ""
            print(f"    {wins}W - {losses}L{push_str} | Win rate: {wr:.1f}%")
        print(f"    Pendientes: {pending}")

    print(f"\n{'=' * 60}")
    print(f"RESUMEN DEL HISTORIAL")
    print(f"{'=' * 60}")
    print(f"  Total picks: {total}")
    _summarize(ml_picks, 'MONEY LINE')
    _summarize(ou_picks, 'OVER/UNDER')

    print(f"\nHistorial guardado en: {HISTORY_FILE}")


if __name__ == '__main__':
    run_verification()
