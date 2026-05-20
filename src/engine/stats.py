"""
Motor de estadisticas: calcula ROI, racha, win rate
a partir del history.json.

Soporta filtros por tier y por bet_type ('moneyline' o 'total').
Stats globales se computan separadamente para ML y O/U.
"""


def american_odds_to_decimal(odds):
    """Convierte cuotas americanas a decimales."""
    if odds is None:
        return None
    try:
        odds = int(odds)
    except (ValueError, TypeError):
        return None
    if odds > 0:
        return 1 + (odds / 100)
    else:
        return 1 + (100 / abs(odds))


def calculate_stats(tracked_picks, last_n_days=None, tier_filter=None, bet_type_filter=None):
    """
    Calcula estadisticas globales o filtradas.

    Args:
        tracked_picks: lista de picks del history.json
        last_n_days: si se especifica, solo considera los ultimos N dias
        tier_filter: si se especifica, solo considera ese tier
        bet_type_filter: 'moneyline', 'total', o None (todos)

    Returns:
        dict con: total, wins, losses, pushes, win_rate, roi, streak, pending
    """
    from datetime import datetime, timedelta
    import pytz

    picks = tracked_picks

    # Filtrar por bet_type
    if bet_type_filter == 'moneyline':
        # Incluir picks sin bet_type (legacy = ML)
        picks = [p for p in picks if p.get('bet_type', 'moneyline') == 'moneyline']
    elif bet_type_filter == 'total':
        picks = [p for p in picks if p.get('bet_type') == 'total']

    # Filtrar por tier
    if tier_filter:
        picks = [p for p in picks if p.get('tier') == tier_filter]

    # Filtrar por ultimos N dias
    if last_n_days:
        tz = pytz.timezone('America/Santo_Domingo')
        cutoff = (datetime.now(tz) - timedelta(days=last_n_days)).strftime('%Y-%m-%d')
        picks = [p for p in picks if p.get('date_played', '') >= cutoff]

    # Verificados (incluyendo pushes)
    verified = [p for p in picks if p.get('result') in ('win', 'loss', 'push')]
    pending = [p for p in picks if p.get('result') is None]

    wins = [p for p in verified if p.get('result') == 'win']
    losses = [p for p in verified if p.get('result') == 'loss']
    pushes = [p for p in verified if p.get('result') == 'push']

    # ROI: stake fijo de 1u por pick
    # Pushes devuelven el stake (no ganan ni pierden)
    # Para denominador de ROI usamos solo wins + losses (pushes no afectan)
    decided = wins + losses
    total_staked = len(decided) * 1.0
    total_returned = 0.0

    for p in wins:
        # Para ML: preferir real_odds (FanDuel Sportsbook) sobre estimated_odds
        # Para O/U: usar odds_american
        if p.get('bet_type') == 'total':
            odds = p.get('odds_american')
        else:
            # Prefiere real_odds si esta disponible (mas preciso)
            odds = p.get('real_odds') or p.get('estimated_odds')
        decimal = american_odds_to_decimal(odds)
        if decimal:
            total_returned += decimal
        else:
            # Fallback: asumir -110 (estandar para O/U y muchos ML)
            total_returned += 1.91

    profit = total_returned - total_staked
    roi = (profit / total_staked * 100) if total_staked > 0 else 0

    # Win rate (pushes no cuentan ni a favor ni en contra)
    win_rate = (len(wins) / len(decided) * 100) if decided else 0

    # Racha actual
    streak = 0
    streak_type = None
    sorted_verified = sorted(
        verified,
        key=lambda x: (x.get('verified_at') or '', x.get('date_played', '')),
        reverse=True
    )
    for p in sorted_verified:
        result = p.get('result')
        if result == 'push':
            continue  # pushes no rompen ni hacen racha
        if streak_type is None:
            streak_type = result
            streak = 1
        elif result == streak_type:
            streak += 1
        else:
            break

    return {
        'total': len(picks),
        'verified': len(verified),
        'pending': len(pending),
        'wins': len(wins),
        'losses': len(losses),
        'pushes': len(pushes),
        'win_rate': round(win_rate, 1),
        'roi': round(roi, 1),
        'profit_units': round(profit, 2),
        'streak': streak,
        'streak_type': streak_type,
    }


def stats_by_tier(tracked_picks, bet_type_filter=None):
    """Calcula stats separadas por cada tier."""
    return {
        'premium': calculate_stats(tracked_picks, tier_filter='premium', bet_type_filter=bet_type_filter),
        'solido': calculate_stats(tracked_picks, tier_filter='solido', bet_type_filter=bet_type_filter),
        'valor': calculate_stats(tracked_picks, tier_filter='valor', bet_type_filter=bet_type_filter),
        'watch': calculate_stats(tracked_picks, tier_filter='watch', bet_type_filter=bet_type_filter),
    }


def get_summary(history):
    """
    Genera resumen completo de stats para inyectar en picks.json.

    Devuelve stats globales + separadas por bet_type (ML y O/U).
    """
    tracked = history.get('tracked_picks', [])

    return {
        # Stats globales (todo mezclado, compatibilidad hacia atras)
        'overall': calculate_stats(tracked),
        'last_30_days': calculate_stats(tracked, last_n_days=30),
        'last_7_days': calculate_stats(tracked, last_n_days=7),
        'by_tier': stats_by_tier(tracked),

        # NUEVO: stats separadas por bet_type
        'moneyline': {
            'overall': calculate_stats(tracked, bet_type_filter='moneyline'),
            'last_30_days': calculate_stats(tracked, last_n_days=30, bet_type_filter='moneyline'),
            'last_7_days': calculate_stats(tracked, last_n_days=7, bet_type_filter='moneyline'),
            'by_tier': stats_by_tier(tracked, bet_type_filter='moneyline'),
        },
        'total': {
            'overall': calculate_stats(tracked, bet_type_filter='total'),
            'last_30_days': calculate_stats(tracked, last_n_days=30, bet_type_filter='total'),
            'last_7_days': calculate_stats(tracked, last_n_days=7, bet_type_filter='total'),
            'by_tier': stats_by_tier(tracked, bet_type_filter='total'),
        },
    }


if __name__ == '__main__':
    import json
    import os

    if not os.path.exists('output/history.json'):
        print("No existe history.json. Corre primero: python -m src.verify_picks")
        exit(1)

    with open('output/history.json', 'r') as f:
        history = json.load(f)

    def _print_stats(name, stats):
        print(f"\n  {name}:")
        print(f"    Total: {stats['total']} | Verificados: {stats['verified']} | Pendientes: {stats['pending']}")
        if stats['verified'] > 0:
            push_str = f", {stats['pushes']}P" if stats.get('pushes') else ""
            print(f"    {stats['wins']}W - {stats['losses']}L{push_str}")
            print(f"    Win rate: {stats['win_rate']}% | ROI: {stats['roi']}% ({stats['profit_units']:+.2f}u)")
            if stats['streak'] > 0:
                print(f"    Racha: {stats['streak']}{(stats['streak_type'] or '')[0].upper()}")

    print("=" * 60)
    print("STATS GLOBALES")
    print("=" * 60)
    _print_stats("OVERALL (ML + O/U)", calculate_stats(history['tracked_picks']))

    print("\n" + "=" * 60)
    print("POR BET_TYPE")
    print("=" * 60)
    _print_stats("MONEY LINE", calculate_stats(history['tracked_picks'], bet_type_filter='moneyline'))
    _print_stats("OVER / UNDER", calculate_stats(history['tracked_picks'], bet_type_filter='total'))
