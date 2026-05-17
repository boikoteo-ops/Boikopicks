"""
Orquestador principal: ejecuta el pipeline completo y genera picks.json
"""
import json
import os
from datetime import datetime
import pytz

from src.fetchers.mlb_schedule import get_mlb_games_today
from src.fetchers.nba_schedule import get_nba_games_today
from src.fetchers.fanduel_odds import get_fanduel_predictions
from src.fetchers.covers_consensus import get_covers_consensus
from src.engine.consensus import merge_game_data, generate_picks, suggest_parlays


def run_pipeline():
    tz = pytz.timezone('America/Santo_Domingo')
    now = datetime.now(tz)

    print("=" * 60)
    print(f"ALMAPICKS — Generacion de picks")
    print(f"Fecha: {now.strftime('%A %d/%m/%Y')}")
    print(f"Hora: {now.strftime('%I:%M %p')} AST")
    print("=" * 60)

    # 1. Schedule MLB
    print("\n[1/4] Obteniendo cartelera MLB...")
    mlb_games = get_mlb_games_today()
    print(f"      Juegos MLB hoy: {len(mlb_games)}")

    # 2. Schedule NBA
    print("\n[2/4] Obteniendo cartelera NBA...")
    nba_games = get_nba_games_today()
    print(f"      Juegos NBA hoy: {len(nba_games)}")

    # 3. Predicciones de fuentes
    print("\n[3/4] Obteniendo predicciones de fuentes...")

    print("  numberFire (FanDuel)...")
    mlb_numberfire = get_fanduel_predictions('mlb')
    nba_numberfire = get_fanduel_predictions('nba')
    print(f"    MLB: {len(mlb_numberfire)} | NBA: {len(nba_numberfire)}")

    print("  Covers Consensus...")
    mlb_covers = get_covers_consensus('mlb')
    nba_covers = get_covers_consensus('nba')
    print(f"    MLB: {len(mlb_covers)} | NBA: {len(nba_covers)}")

    # 4. Cruce y picks
    print("\n[4/4] Cruzando datos y generando picks...")

    mlb_merged = merge_game_data(mlb_games, mlb_numberfire, mlb_covers)
    nba_merged = merge_game_data(nba_games, nba_numberfire, nba_covers)

    all_games = mlb_merged + nba_merged

    picks = generate_picks(all_games)
    parlays = suggest_parlays(picks)

    print(f"      Total juegos analizados: {len(all_games)}")
    print(f"      Picks recomendados: {len(picks)}")

    # Output
    output = {
        'generated_at': now.isoformat(),
        'date_display': now.strftime('%d/%m/%Y'),
        'summary': {
            'total_games_mlb': len(mlb_games),
            'total_games_nba': len(nba_games),
            'total_picks': len(picks),
            'sports_active': [s for s, count in [('MLB', len(mlb_games)), ('NBA', len(nba_games))] if count > 0],
            'sources_used': ['numberFire', 'Covers Consensus'],
        },
        'games': all_games,
        'picks': picks,
        'parlays': parlays,
    }

    # Guardar
    os.makedirs('output', exist_ok=True)
    output_path = 'output/picks.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nPicks guardados en: {output_path}")

    # Resumen
    if picks:
        by_tier = {'premium': [], 'solido': [], 'valor': [], 'watch': []}
        for p in picks:
            by_tier[p['tier']].append(p)

        print("\n" + "=" * 60)
        print(f"PICKS DE HOY ({len(picks)} en total)")
        print("=" * 60)

        for tier_key, tier_emoji in [('premium', 'PREMIUM'), ('solido', 'SOLIDO'),
                                       ('valor', 'VALOR'), ('watch', 'WATCH')]:
            tier_picks = by_tier[tier_key]
            if not tier_picks:
                continue
            print(f"\n-- {tier_emoji} ({len(tier_picks)}) --")
            for p in tier_picks:
                agree_mark = ''
                if p.get('sources_agree') is True:
                    agree_mark = ' [2/2 fuentes]'
                elif p.get('sources_agree') is False:
                    agree_mark = ' [fuentes disienten]'
                elif p.get('sources_count', 0) == 1:
                    agree_mark = ' [1/2 fuentes]'
                print(f"  [{p['sport']}] {p['pick']:.<32} {p['model_prob']}% | edge +{p['edge']}% | conf {p['confidence']}{agree_mark}")
                print(f"       {p['game']} ({p['start_time']})")

        if parlays:
            print("\n" + "=" * 60)
            print("PARLEYS SUGERIDOS")
            print("=" * 60)
            for nombre, parlay in parlays.items():
                print(f"\n{nombre.upper()} ({len(parlay['legs'])} patas) - prob. {parlay['probability']}%:")
                for leg in parlay['legs']:
                    print(f"  - {leg['pick']} [{leg['tier']}]")
    else:
        print("\nNo se generaron picks.")

    return output


if __name__ == '__main__':
    run_pipeline()