"""
Motor de consenso: combina schedule + predicciones del modelo
para generar picks con score de confianza.
"""


def american_odds_to_implied_prob(odds):
    """
    Convierte cuotas americanas a probabilidad implícita.
    Ejemplo: -132 → 56.9%, +132 → 43.1%
    """
    if odds is None:
        return None
    if odds < 0:
        return abs(odds) / (abs(odds) + 100) * 100
    else:
        return 100 / (odds + 100) * 100


def implied_prob_to_american_odds(prob):
    """
    Convierte probabilidad (%) a cuota americana aproximada.
    """
    if prob is None or prob <= 0 or prob >= 100:
        return None
    p = prob / 100
    if p >= 0.5:
        return round(-p / (1 - p) * 100)
    else:
        return round((1 - p) / p * 100)


def _normalize_team_name(name):
    """Normaliza nombre de equipo para comparación."""
    if not name:
        return ''
    return name.lower().strip().replace('.', '')


def _teams_match(name1, name2):
    """Verifica si dos nombres de equipo refieren al mismo equipo."""
    n1 = _normalize_team_name(name1)
    n2 = _normalize_team_name(name2)
    if not n1 or not n2:
        return False
    # Match exacto o uno contiene al otro
    return n1 == n2 or n1 in n2 or n2 in n1


def merge_game_data(schedule_games, model_predictions):
    """
    Combina juegos del schedule con predicciones del modelo.
    Retorna lista de juegos enriquecidos.
    """
    merged = []

    for game in schedule_games:
        enriched = dict(game)  # copia
        enriched['home_prob_model'] = None
        enriched['away_prob_model'] = None
        enriched['has_model_prediction'] = False

        for pred in model_predictions:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['home_prob_model'] = pred['home_prob_model']
                enriched['away_prob_model'] = pred['away_prob_model']
                enriched['has_model_prediction'] = True
                break

        merged.append(enriched)

    return merged


def generate_picks(games, min_model_prob=52.0):
    """
    Genera lista completa de picks recomendados, clasificados por confianza.

    Tiers de confianza:
    - 🔥 Premium  (modelo ≥62% y edge ≥1.8%)
    - ⭐ Sólido   (modelo ≥58% y edge ≥1.2%)
    - 💡 Valor    (modelo ≥55% y edge ≥0.8%)
    - 👀 Watch    (modelo ≥52%, sin edge claro)
    """
    picks = []

    for game in games:
        if not game.get('has_model_prediction'):
            continue

        home_prob = game['home_prob_model']
        away_prob = game['away_prob_model']

        if home_prob >= away_prob:
            model_pick = game['home']
            model_prob = home_prob
            side = 'home'
        else:
            model_pick = game['away']
            model_prob = away_prob
            side = 'away'

        if model_prob < min_model_prob:
            continue

        # Estimar implícita del mercado (vig promedio ~5%)
        market_juice = (model_prob - 50) * 0.15
        estimated_market_prob = model_prob - market_juice
        edge = model_prob - estimated_market_prob

        # Clasificar por tier
        if model_prob >= 62 and edge >= 1.8:
            tier = 'premium'
            tier_label = '🔥 Premium'
        elif model_prob >= 58 and edge >= 1.2:
            tier = 'solido'
            tier_label = '⭐ Sólido'
        elif model_prob >= 55 and edge >= 0.8:
            tier = 'valor'
            tier_label = '💡 Valor'
        else:
            tier = 'watch'
            tier_label = '👀 Watch'

        # Score de confianza (0-100)
        confidence = (model_prob - 50) * 2 + edge * 3
        confidence = max(0, min(100, round(confidence, 1)))

        picks.append({
            'sport': game['sport'],
            'game': f"{game['away']} @ {game['home']}",
            'home': game['home'],
            'away': game['away'],
            'pick': model_pick,
            'side': side,
            'start_time': game.get('start_time', 'TBD'),
            'model_prob': round(model_prob, 1),
            'estimated_implied_prob': round(estimated_market_prob, 1),
            'edge': round(edge, 1),
            'confidence': confidence,
            'tier': tier,
            'tier_label': tier_label,
            'estimated_odds': implied_prob_to_american_odds(estimated_market_prob),
            'home_pitcher': game.get('home_pitcher'),
            'away_pitcher': game.get('away_pitcher'),
        })

    picks.sort(key=lambda x: x['confidence'], reverse=True)
    return picks


def suggest_parlays(picks):
    """
    Sugiere parleys solo con picks de tier premium/sólido/valor.
    """
    quality_picks = [p for p in picks if p['tier'] in ('premium', 'solido', 'valor')]

    if len(quality_picks) < 3:
        return {}

    parlays = {}

    if len(quality_picks) >= 3:
        conservative = quality_picks[:3]
        prob = 1
        for p in conservative:
            prob *= (p['model_prob'] / 100)
        parlays['conservador'] = {
            'legs': [{'pick': p['pick'], 'game': p['game'], 'tier': p['tier']} for p in conservative],
            'probability': round(prob * 100, 1),
        }

    if len(quality_picks) >= 4:
        balanced = quality_picks[:4]
        prob = 1
        for p in balanced:
            prob *= (p['model_prob'] / 100)
        parlays['balanceado'] = {
            'legs': [{'pick': p['pick'], 'game': p['game'], 'tier': p['tier']} for p in balanced],
            'probability': round(prob * 100, 1),
        }

    if len(quality_picks) >= 6:
        aggressive = quality_picks[:6]
        prob = 1
        for p in aggressive:
            prob *= (p['model_prob'] / 100)
        parlays['agresivo'] = {
            'legs': [{'pick': p['pick'], 'game': p['game'], 'tier': p['tier']} for p in aggressive],
            'probability': round(prob * 100, 1),
        }

    return parlays


if __name__ == '__main__':
    # Prueba con datos dummy
    print("Test del motor de consenso:")
    print(f"  Cuota -132 = {american_odds_to_implied_prob(-132):.1f}% implícita")
    print(f"  Cuota +150 = {american_odds_to_implied_prob(150):.1f}% implícita")
    print(f"  60% modelo = cuota ~{implied_prob_to_american_odds(60)}")