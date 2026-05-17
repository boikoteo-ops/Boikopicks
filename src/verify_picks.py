"""
Verifica resultados de picks previos y actualiza el historial.
Corre cada noche para procesar los picks del dia anterior.
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


def verify_pick(pick, results):
    """
    Verifica si un pick gano o perdio.
    Retorna 'win', 'loss' o None.
    """
    for result in results:
        if (_teams_match(pick['home'], result['home']) and
            _teams_match(pick['away'], result['away'])):
            return 'win' if _teams_match(pick['pick'], result['winner']) else 'loss'
    return None


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
    """
    if not os.path.exists('output/picks.json'):
        print("No existe output/picks.json")
        return history

    with open('output/picks.json', 'r', encoding='utf-8') as f:
        picks_data = json.load(f)

    tz = pytz.timezone('America/Santo_Domingo')
    today_str = datetime.now(tz).strftime('%Y-%m-%d')

    existing_ids = {
        (p.get('date_played'), p.get('pick'), p.get('home'), p.get('away'))
        for p in history['tracked_picks']
    }

    added = 0
    for pick in picks_data.get('picks', []):
        key = (today_str, pick['pick'], pick['home'], pick['away'])
        if key in existing_ids:
            continue

        history['tracked_picks'].append({
            'date_played': today_str,
            'sport': pick['sport'],
            'pick': pick['pick'],
            'home': pick['home'],
            'away': pick['away'],
            'side': pick['side'],
            'tier': pick['tier'],
            'model_prob': pick['model_prob'],
            'edge': pick['edge'],
            'confidence': pick['confidence'],
            'estimated_odds': pick.get('estimated_odds'),
            'sources_agree': pick.get('sources_agree'),
            'sources_count': pick.get('sources_count'),
            'result': None,
            'verified_at': None,
            'tracked_at': datetime.now(tz).isoformat(),
        })
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

    # Cargar historial UNA SOLA VEZ
    history = load_history()

    # 1. Agregar picks de hoy al tracking
    print("\n[1/3] Agregando picks de hoy al tracking...")
    history = add_todays_picks_to_tracking(history)

    # 2. Verificar picks de ayer
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    print(f"\n[2/3] Verificando picks de {yesterday_str}...")
    history = verify_picks_for_date(history, yesterday_str)

    # 3. Catch-up de antier
    day_before = now - timedelta(days=2)
    day_before_str = day_before.strftime('%Y-%m-%d')
    print(f"\n[3/3] Verificando picks de {day_before_str} (catch-up)...")
    history = verify_picks_for_date(history, day_before_str)

    # Guardar
    history['last_update'] = now.isoformat()
    save_history(history)

    # Resumen
    total = len(history['tracked_picks'])
    verified = sum(1 for p in history['tracked_picks'] if p.get('result') is not None)
    wins = sum(1 for p in history['tracked_picks'] if p.get('result') == 'win')
    losses = sum(1 for p in history['tracked_picks'] if p.get('result') == 'loss')
    pending = total - verified

    print(f"\n{'=' * 60}")
    print(f"RESUMEN DEL HISTORIAL")
    print(f"{'=' * 60}")
    print(f"  Picks totales rastreados: {total}")
    print(f"  Verificados: {verified}")
    print(f"    Wins:   {wins}")
    print(f"    Losses: {losses}")
    if verified > 0:
        win_rate = (wins / verified) * 100
        print(f"    Win rate: {win_rate:.1f}%")
    print(f"  Pendientes: {pending}")
    print(f"\nHistorial guardado en: {HISTORY_FILE}")


if __name__ == '__main__':
    run_verification()