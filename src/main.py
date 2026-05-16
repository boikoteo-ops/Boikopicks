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
from src.engine.consensus import merge_game_data, generate_picks, suggest_parlays


def run_pipeline():
    tz = pytz.timezone('America/Santo_Domingo')
    now = datetime.now(tz)

    print("=" * 60)
    print(f"BOIKOPICKS — Generación de picks")
    print(f"Fecha: {now.strftime('%A %d/%m/%Y')}")
    print(f"Hora: {now.strftime('%I:%M %p')} AST")
    print("=" * 60)

    # ─── 1. Schedule MLB ───
    print("\n[1/4] Obteniendo cartelera MLB...")
    mlb_games = get_mlb_games_today()
    print(f"      Juegos MLB hoy: {len(mlb_games)}")

    # ─── 2. Schedule NBA ───
    print("\n[2/4] Obteniendo cartelera NBA...")
    nba_games = get_nba_games_today()
    print(f"      Juegos NBA hoy: {len(nba_games)}")

    # ─── 3. Predicciones del modelo ───
    print("\n[3/4] Obteniendo predicciones del modelo...")
    mlb_predictions = get_fanduel_predictions('mlb')
    nba_predictions = get_fanduel_predictions('nba')
    print(f"      Predicciones MLB: {len(mlb_predictions)}")
    print(f"      Predicciones NBA: {len(nba_predictions)}")

    # ─── 4. Cruce y generación de picks ───
    print("\n[4/4] Cruzando datos y generando picks...")

    mlb_merged = merge_game_data(mlb_games, mlb_predictions)
    nba_merged = merge_game_data(nba_games, nba_predictions)

    all_games = mlb_merged + nba_merged

    picks = generate_picks(all_games)
    parlays = suggest_parlays(picks)

    print(f"      Total juegos analizados: {len(all_games)}")
    print(f"      Picks recomendados: {len(picks)}")

    # ─── Construir output ───
    output = {
        'generated_at': now.isoformat(),
        'date_display': now.strftime('%d/%m/%Y'),
        'summary': {
            'total_games_mlb': len(mlb_games),
            'total_games_nba': len(nba_games),
            'total_picks': len(picks),
            'sports_active': [s for s, count in [('MLB', len(mlb_games)), ('NBA', len(nba_games))] if count > 0],
        },
        'games': all_games,
        'picks': picks,
        'parlays': parlays,
    }

    # ─── Guardar a archivo ───
    os.makedirs('output', exist_ok=True)
    output_path = 'output/picks.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Picks guardados en: {output_path}")

    # ─── Imprimir resumen ───
    if picks:
        print("\n" + "=" * 60)
        print("TOP PICKS DE HOY")
        print("=" * 60)
        for i, p in enumerate(picks[:5], 1):
            print(f"\n#{i}  [{p['sport']}] {p['pick']}")
            print(f"     {p['game']} — {p['start_time']}")
            print(f"     Modelo: {p['model_prob']}% | Edge: +{p['edge']}% | Confianza: {p['confidence']}")
            print(f"     Cuota estimada: {p['estimated_odds']:+d}" if p['estimated_odds'] else "")

        if parlays:
            print("\n" + "=" * 60)
            print("PARLEYS SUGERIDOS")
            print("=" * 60)
            for nombre, parlay in parlays.items():
                print(f"\n{nombre.upper()} ({len(parlay['legs'])} patas):")
                for leg in parlay['legs']:
                    print(f"  • {leg['pick']}")
                print(f"  Probabilidad: {parlay['probability']}%")
    else:
        print("\n⚠ No se generaron picks. Posibles razones:")
        print("  - No hay juegos hoy")
        print("  - Las fuentes están caídas")
        print("  - Los favoritos no alcanzan el umbral mínimo de confianza")

    return output


if __name__ == '__main__':
    run_pipeline()