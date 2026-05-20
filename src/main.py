"""
Orquestador principal: ejecuta el pipeline completo y genera picks.json.

Incluye picks de Money Line + Over/Under (Fase 6 — totales).
"""
import json
import os
from datetime import datetime, timedelta
import pytz

from src.fetchers.mlb_schedule import get_mlb_games_today
from src.fetchers.nba_schedule import get_nba_games_today
from src.fetchers.fanduel_odds import get_fanduel_predictions
from src.fetchers.covers_consensus import get_covers_consensus, get_covers_totals
from src.fetchers.pickswise import get_pickswise_picks, get_pickswise_totals
from src.fetchers.dratings import get_dratings_predictions
from src.engine.consensus import (
    merge_game_data, generate_picks, suggest_parlays,
    merge_ou_data, generate_ou_picks,
)
from src.engine.stats import get_summary
from src.verify_picks import (
    load_history,
    save_history,
    add_todays_picks_to_tracking,
    verify_picks_for_date,
)


def run_pipeline():
    tz = pytz.timezone('America/Santo_Domingo')
    now = datetime.now(tz)

    print("=" * 60)
    print(f"ALMAPICKS — Generacion de picks")
    print(f"Fecha: {now.strftime('%A %d/%m/%Y')}")
    print(f"Hora: {now.strftime('%I:%M %p')} AST")
    print("=" * 60)

    # 1. Schedule MLB
    print("\n[1/5] Obteniendo cartelera MLB...")
    mlb_games = get_mlb_games_today()
    print(f"      Juegos MLB hoy: {len(mlb_games)}")

    # 2. Schedule NBA
    print("\n[2/5] Obteniendo cartelera NBA...")
    nba_games = get_nba_games_today()
    print(f"      Juegos NBA hoy: {len(nba_games)}")

    # 3. Predicciones (4 fuentes ML + 3 fuentes O/U para MLB)
    print("\n[3/5] Obteniendo predicciones de fuentes...")

    print("  numberFire (FanDuel)...")
    mlb_numberfire = get_fanduel_predictions('mlb')
    nba_numberfire = get_fanduel_predictions('nba')
    print(f"    MLB: {len(mlb_numberfire)} | NBA: {len(nba_numberfire)}")

    print("  Covers Consensus...")
    mlb_covers = get_covers_consensus('mlb')
    nba_covers = get_covers_consensus('nba')
    mlb_covers_ou = get_covers_totals('mlb')  # NUEVO: O/U para MLB
    print(f"    MLB: {len(mlb_covers)} | NBA: {len(nba_covers)} | MLB O/U: {len(mlb_covers_ou)}")

    print("  Pickswise (handicappers)...")
    mlb_pickswise = get_pickswise_picks('mlb')
    nba_pickswise = get_pickswise_picks('nba')
    mlb_pickswise_ou = get_pickswise_totals('mlb')  # NUEVO: O/U para MLB
    print(f"    MLB: {len(mlb_pickswise)} | NBA: {len(nba_pickswise)} | MLB O/U: {len(mlb_pickswise_ou)}")

    print("  DRatings (Elo + ML)...")
    mlb_dratings = get_dratings_predictions('mlb')
    nba_dratings = get_dratings_predictions('nba')
    # DRatings ya trae O/U embebido en sus dicts (campos ou_pick, ou_line, etc.)
    print(f"    MLB: {len(mlb_dratings)} | NBA: {len(nba_dratings)}")

    # 4. Cruce y picks
    print("\n[4/5] Cruzando datos y generando picks...")

    # ---- Money Line (sin cambios) ----
    mlb_merged = merge_game_data(
        mlb_games, mlb_numberfire, mlb_covers, mlb_pickswise, mlb_dratings
    )
    nba_merged = merge_game_data(
        nba_games, nba_numberfire, nba_covers, nba_pickswise, nba_dratings
    )

    all_games = mlb_merged + nba_merged

    ml_picks = generate_picks(all_games)

    # ---- Over/Under (NUEVO — solo MLB por ahora) ----
    mlb_ou_merged = merge_ou_data(
        mlb_games, mlb_dratings, mlb_pickswise_ou, mlb_covers_ou
    )
    ou_picks = generate_ou_picks(mlb_ou_merged)

    # ---- Mezclar y ordenar por confianza ----
    picks = ml_picks + ou_picks
    picks.sort(key=lambda x: x['confidence'], reverse=True)

    # Parleys siguen siendo solo de ML por ahora
    parlays = suggest_parlays(ml_picks)

    print(f"      Total juegos analizados: {len(all_games)}")
    print(f"      Picks ML: {len(ml_picks)} | Picks O/U: {len(ou_picks)}")
    print(f"      Picks recomendados: {len(picks)}")

    output = {
        'generated_at': now.isoformat(),
        'date_display': now.strftime('%d/%m/%Y'),
        'summary': {
            'total_games_mlb': len(mlb_games),
            'total_games_nba': len(nba_games),
            'total_picks': len(picks),
            'total_picks_ml': len(ml_picks),
            'total_picks_ou': len(ou_picks),
            'sports_active': [s for s, count in [('MLB', len(mlb_games)), ('NBA', len(nba_games))] if count > 0],
            'sources_used': ['numberFire', 'Covers Consensus', 'Pickswise', 'DRatings'],
            'sources_ou_used': ['DRatings', 'Pickswise', 'Covers'],
        },
        'games': all_games,
        'games_ou': mlb_ou_merged,  # detalle O/U para depurar / frontend
        'picks': picks,
        'parlays': parlays,
    }

    os.makedirs('output', exist_ok=True)
    with open('output/picks.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # 5. Tracking y stats
    print("\n[5/5] Tracking y stats...")
    history = load_history()
    history = add_todays_picks_to_tracking(history)

    yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    day_before_str = (now - timedelta(days=2)).strftime('%Y-%m-%d')
    history = verify_picks_for_date(history, yesterday_str)
    history = verify_picks_for_date(history, day_before_str)

    history['last_update'] = now.isoformat()
    save_history(history)

    stats = get_summary(history)

    output['stats'] = stats
    with open('output/picks.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nPicks guardados en: output/picks.json")
    print(f"Historial guardado en: output/history.json")

    # Resumen
    if picks:
        by_tier = {'premium': [], 'solido': [], 'valor': [], 'watch': []}
        for p in picks:
            by_tier[p['tier']].append(p)

        print("\n" + "=" * 60)
        print(f"PICKS DE HOY ({len(picks)} en total — {len(ml_picks)} ML + {len(ou_picks)} O/U)")
        print("=" * 60)

        for tier_key, tier_emoji in [('premium', 'PREMIUM'), ('solido', 'SOLIDO'),
                                       ('valor', 'VALOR'), ('watch', 'WATCH')]:
            tier_picks = by_tier[tier_key]
            if not tier_picks:
                continue
            print(f"\n-- {tier_emoji} ({len(tier_picks)}) --")
            for p in tier_picks:
                if p.get('bet_type') == 'total':
                    # Pick O/U
                    arrow = '▲' if p['side'] == 'over' else '▼'
                    line = p.get('line', '?')
                    diverge = ' ⚠divergen' if p.get('lines_diverge') else ''
                    print(f"  [{p['sport']}] {p['game']:.<40} {arrow} {p['pick']} {line} | conf {p['confidence']} [{p['agree_count']}/{p['sources_count']}]{diverge}")
                else:
                    # Pick ML (formato original)
                    sc = p.get('sources_count', 0)
                    badges = f"[{sc}/4"
                    if p.get('sources_unanimous'):
                        badges += " ✓✓"
                    elif p.get('sources_agree'):
                        badges += " ✓"
                    elif p.get('sources_agree') is False:
                        badges += " ⚠"
                    badges += "]"
                    if p.get('has_pickswise'):
                        badges += f" PW:{p['pickswise_confidence']}⭐"
                    if p.get('has_dratings'):
                        badges += f" DR:{p['dratings_prob']}%"
                    print(f"  [{p['sport']}] {p['pick']:.<32} {p['model_prob']}% | edge +{p['edge']}% | conf {p['confidence']} {badges}")

        print(f"\n{'=' * 60}")
        print(f"STATS HISTORICAS")
        print(f"{'=' * 60}")
        overall = stats['overall']
        print(f"Total rastreado: {overall['total']} picks")
        print(f"Verificados:     {overall['verified']}")
        if overall['verified'] > 0:
            print(f"  Win rate: {overall['win_rate']}%")
            print(f"  ROI:      {overall['roi']}% ({overall['profit_units']:+.2f}u)")
            if overall['streak'] > 0:
                print(f"  Racha:    {overall['streak']}{(overall['streak_type'] or '')[0].upper()}")
        print(f"Pendientes:      {overall['pending']}")
    else:
        print("\nNo se generaron picks.")

    return output


if __name__ == '__main__':
    run_pipeline()
