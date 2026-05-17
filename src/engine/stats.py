"""
Motor de estadisticas: calcula ROI, racha, win rate por tier
a partir del history.json.
"""


def american_odds_to_decimal(odds):
    """Convierte cuotas americanas a decimales."""
    if odds is None:
        return None
    if odds > 0:
        return 1 + (odds / 100)
    else:
        return 1 + (100 / abs(odds))


def calculate_stats(tracked_picks, last_n_days=None, tier_filter=None):
    """
    Calcula estadisticas globales o filtradas.

    Args:
        tracked_picks: lista de picks del history.json
        last_n_days: si se especifica, solo considera los ultimos N dias
        tier_filter: si se especifica, solo considera ese tier

    Returns:
        dict con: total, wins, losses, win_rate, roi, streak, pending
    """
    from datetime import datetime, timedelta
    import pytz

    # Filtrar por tier
    picks = tracked_picks
    if tier_filter:
        picks = [p for p in picks if p.get('tier') == tier_filter]

    # Filtrar por ultimos N dias
    if last_n_days:
        tz = pytz.timezone('America/Santo_Domingo')
        cutoff = (datetime.now(tz) - timedelta(days=last_n_days)).strftime('%Y-%m-%d')
        picks = [p for p in picks if p.get('date_played', '') >= cutoff]

    # Solo verificados para win rate y ROI
    verified = [p for p in picks if p.get('result') in ('win', 'loss')]
    pending = [p for p in picks if p.get('result') is None]

    wins = [p for p in verified if p.get('result') == 'win']
    losses = [p for p in verified if p.get('result') == 'loss']

    # ROI: asumimos stake fijo de 1u por pick
    total_staked = len(verified) * 1.0
    total_returned = 0.0
    for p in wins:
        odds = p.get('estimated_odds')
        decimal = american_odds_to_decimal(odds)
        if decimal:
            total_returned += decimal  # devuelve stake + ganancia
        # Si no hay odds, asumimos -110 (decimal 1.91)
        elif odds is None:
            total_returned += 1.91

    # Las losses no devuelven nada (perdiste el stake)
    profit = total_returned - total_staked
    roi = (profit / total_staked * 100) if total_staked > 0 else 0

    # Racha actual (consecutiva desde el ultimo verificado hacia atras)
    streak = 0
    streak_type = None
    sorted_verified = sorted(
        verified,
        key=lambda x: (x.get('verified_at') or '', x.get('date_played', '')),
        reverse=True
    )
    for p in sorted_verified:
        if streak_type is None:
            streak_type = p.get('result')
            streak = 1
        elif p.get('result') == streak_type:
            streak += 1
        else:
            break

    win_rate = (len(wins) / len(verified) * 100) if verified else 0

    return {
        'total': len(picks),
        'verified': len(verified),
        'pending': len(pending),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(win_rate, 1),
        'roi': round(roi, 1),
        'profit_units': round(profit, 2),
        'streak': streak,
        'streak_type': streak_type,  # 'win' o 'loss'
    }


def stats_by_tier(tracked_picks):
    """Calcula stats separadas por cada tier."""
    return {
        'premium': calculate_stats(tracked_picks, tier_filter='premium'),
        'solido': calculate_stats(tracked_picks, tier_filter='solido'),
        'valor': calculate_stats(tracked_picks, tier_filter='valor'),
        'watch': calculate_stats(tracked_picks, tier_filter='watch'),
    }


def get_summary(history):
    """
    Genera resumen completo de stats para inyectar en picks.json.
    """
    tracked = history.get('tracked_picks', [])

    return {
        'overall': calculate_stats(tracked),
        'last_30_days': calculate_stats(tracked, last_n_days=30),
        'last_7_days': calculate_stats(tracked, last_n_days=7),
        'by_tier': stats_by_tier(tracked),
    }


if __name__ == '__main__':
    import json
    import os

    if not os.path.exists('output/history.json'):
        print("No existe history.json. Corre primero: python -m src.verify_picks")
        exit(1)

    with open('output/history.json', 'r') as f:
        history = json.load(f)

    print("=== STATS GLOBALES ===")
    overall = calculate_stats(history['tracked_picks'])
    print(f"Total: {overall['total']}")
    print(f"Verificados: {overall['verified']}")
    print(f"  Wins: {overall['wins']}")
    print(f"  Losses: {overall['losses']}")
    print(f"  Win rate: {overall['win_rate']}%")
    print(f"  ROI: {overall['roi']}% ({overall['profit_units']:+.2f}u)")
    print(f"  Racha: {overall['streak']}{overall['streak_type'] or '-'}")
    print(f"Pendientes: {overall['pending']}")

    print("\n=== POR TIER ===")
    by_tier = stats_by_tier(history['tracked_picks'])
    for tier_name, tier_stats in by_tier.items():
        if tier_stats['total'] == 0:
            continue
        print(f"\n{tier_name.upper()}:")
        print(f"  Picks: {tier_stats['total']} (verificados: {tier_stats['verified']})")
        if tier_stats['verified'] > 0:
            print(f"  Win rate: {tier_stats['win_rate']}%")
            print(f"  ROI: {tier_stats['roi']}%")