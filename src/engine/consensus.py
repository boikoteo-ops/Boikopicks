"""
Motor de consenso: combina schedule + numberFire + Covers + Pickswise + DRatings.
Genera picks con score de confianza y acuerdo entre fuentes.
"""


def american_odds_to_implied_prob(odds):
    if odds is None:
        return None
    if odds < 0:
        return abs(odds) / (abs(odds) + 100) * 100
    else:
        return 100 / (odds + 100) * 100


def implied_prob_to_american_odds(prob):
    if prob is None or prob <= 0 or prob >= 100:
        return None
    p = prob / 100
    if p >= 0.5:
        return round(-p / (1 - p) * 100)
    else:
        return round((1 - p) / p * 100)


def _normalize_team_name(name):
    if not name:
        return ''
    return name.lower().strip().replace('.', '')


def _teams_match(name1, name2):
    n1 = _normalize_team_name(name1)
    n2 = _normalize_team_name(name2)
    if not n1 or not n2:
        return False
    return n1 == n2 or n1 in n2 or n2 in n1


def merge_game_data(schedule_games, numberfire_predictions, covers_predictions,
                     pickswise_predictions=None, dratings_predictions=None):
    """
    Combina juegos del schedule con predicciones de 4 fuentes.
    pickswise y dratings son opcionales.
    """
    if pickswise_predictions is None:
        pickswise_predictions = []
    if dratings_predictions is None:
        dratings_predictions = []

    merged = []

    for game in schedule_games:
        enriched = dict(game)

        # numberFire
        enriched['home_prob_numberfire'] = None
        enriched['away_prob_numberfire'] = None
        enriched['has_numberfire'] = False

        for pred in numberfire_predictions:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['home_prob_numberfire'] = pred['home_prob_model']
                enriched['away_prob_numberfire'] = pred['away_prob_model']
                enriched['has_numberfire'] = True
                break

        # Covers
        enriched['home_pct_covers'] = None
        enriched['away_pct_covers'] = None
        enriched['has_covers'] = False

        for pred in covers_predictions:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['home_pct_covers'] = pred['home_pct_public']
                enriched['away_pct_covers'] = pred['away_pct_public']
                enriched['has_covers'] = True
                break

        # Pickswise
        enriched['home_prob_pickswise'] = None
        enriched['away_prob_pickswise'] = None
        enriched['pickswise_confidence'] = None
        enriched['pickswise_pick_team'] = None
        enriched['has_pickswise'] = False

        for pred in pickswise_predictions:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['home_prob_pickswise'] = pred['home_prob_pickswise']
                enriched['away_prob_pickswise'] = pred['away_prob_pickswise']
                enriched['pickswise_confidence'] = pred['confidence']
                enriched['pickswise_pick_team'] = pred['pick_team']
                enriched['has_pickswise'] = True
                break

        # DRatings (NUEVA 4ta fuente)
        enriched['home_prob_dratings'] = None
        enriched['away_prob_dratings'] = None
        enriched['dratings_total_runs'] = None
        enriched['dratings_home_runs'] = None
        enriched['dratings_away_runs'] = None
        enriched['has_dratings'] = False

        for pred in dratings_predictions:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['home_prob_dratings'] = pred['home_prob']
                enriched['away_prob_dratings'] = pred['away_prob']
                enriched['dratings_total_runs'] = pred.get('total_runs')
                enriched['dratings_home_runs'] = pred.get('home_runs_expected')
                enriched['dratings_away_runs'] = pred.get('away_runs_expected')
                enriched['has_dratings'] = True
                break

        # Promedio de las fuentes disponibles
        sources_count = 0
        home_prob_sum = 0
        away_prob_sum = 0

        if enriched['has_numberfire']:
            home_prob_sum += enriched['home_prob_numberfire']
            away_prob_sum += enriched['away_prob_numberfire']
            sources_count += 1

        if enriched['has_covers']:
            home_prob_sum += enriched['home_pct_covers']
            away_prob_sum += enriched['away_pct_covers']
            sources_count += 1

        if enriched['has_pickswise']:
            home_prob_sum += enriched['home_prob_pickswise']
            away_prob_sum += enriched['away_prob_pickswise']
            sources_count += 1

        if enriched['has_dratings']:
            home_prob_sum += enriched['home_prob_dratings']
            away_prob_sum += enriched['away_prob_dratings']
            sources_count += 1

        if sources_count > 0:
            enriched['home_prob_model'] = round(home_prob_sum / sources_count, 1)
            enriched['away_prob_model'] = round(away_prob_sum / sources_count, 1)
            enriched['has_model_prediction'] = True
        else:
            enriched['home_prob_model'] = None
            enriched['away_prob_model'] = None
            enriched['has_model_prediction'] = False

        enriched['sources_count'] = sources_count
        enriched['sources_total'] = 4  # max posible ahora

        # Acuerdo entre fuentes (cuantas pickean al mismo equipo)
        if sources_count >= 2:
            picks_home = 0
            picks_away = 0
            if enriched['has_numberfire']:
                if enriched['home_prob_numberfire'] > enriched['away_prob_numberfire']:
                    picks_home += 1
                else:
                    picks_away += 1
            if enriched['has_covers']:
                if enriched['home_pct_covers'] > enriched['away_pct_covers']:
                    picks_home += 1
                else:
                    picks_away += 1
            if enriched['has_pickswise']:
                if enriched['home_prob_pickswise'] > enriched['away_prob_pickswise']:
                    picks_home += 1
                else:
                    picks_away += 1
            if enriched['has_dratings']:
                if enriched['home_prob_dratings'] > enriched['away_prob_dratings']:
                    picks_home += 1
                else:
                    picks_away += 1

            enriched['sources_agree'] = (picks_home == sources_count or picks_away == sources_count)
            enriched['sources_unanimous'] = enriched['sources_agree'] and sources_count >= 3
        else:
            enriched['sources_agree'] = None
            enriched['sources_unanimous'] = False

        merged.append(enriched)

    return merged


def generate_picks(games, min_model_prob=52.0):
    """Genera lista de picks clasificados por tier."""
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

        market_juice = (model_prob - 50) * 0.15
        estimated_market_prob = model_prob - market_juice
        edge = model_prob - estimated_market_prob

        # Tier inicial
        if model_prob >= 62 and edge >= 1.8:
            tier = 'premium'
            tier_label = 'Premium'
        elif model_prob >= 58 and edge >= 1.2:
            tier = 'solido'
            tier_label = 'Solido'
        elif model_prob >= 55 and edge >= 0.8:
            tier = 'valor'
            tier_label = 'Valor'
        else:
            tier = 'watch'
            tier_label = 'Watch'

        # Ajuste segun consenso
        sources_count = game.get('sources_count', 0)
        sources_agree = game.get('sources_agree')
        sources_unanimous = game.get('sources_unanimous', False)

        # Bonus tier si 4/4 coinciden
        if sources_count == 4 and sources_agree is True:
            if tier == 'solido':
                tier = 'premium'
                tier_label = 'Premium'
            elif tier == 'valor':
                tier = 'solido'
                tier_label = 'Solido'
        # Bonus tier si 3/3 coinciden
        elif sources_count == 3 and sources_agree is True:
            if tier == 'solido':
                tier = 'premium'
                tier_label = 'Premium'
            elif tier == 'valor':
                tier = 'solido'
                tier_label = 'Solido'
        # Penalizacion si disienten
        elif sources_agree is False:
            if tier == 'premium':
                tier = 'solido'
                tier_label = 'Solido'
            elif tier == 'solido':
                tier = 'valor'
                tier_label = 'Valor'
            elif tier == 'valor':
                tier = 'watch'
                tier_label = 'Watch'

        # Confianza
        confidence = (model_prob - 50) * 2 + edge * 3
        if sources_agree is True and sources_count == 4:
            confidence += 15  # bonus extra por 4/4
        elif sources_agree is True and sources_count == 3:
            confidence += 10
        elif sources_agree is True and sources_count == 2:
            confidence += 5
        elif sources_agree is False:
            confidence -= 10
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
            'sources_count': game.get('sources_count', 0),
            'sources_total': game.get('sources_total', 4),
            'sources_agree': game.get('sources_agree'),
            'sources_unanimous': game.get('sources_unanimous', False),
            'numberfire_prob': game.get('home_prob_numberfire') if side == 'home' else game.get('away_prob_numberfire'),
            'covers_pct': game.get('home_pct_covers') if side == 'home' else game.get('away_pct_covers'),
            'pickswise_prob': game.get('home_prob_pickswise') if side == 'home' else game.get('away_prob_pickswise'),
            'pickswise_confidence': game.get('pickswise_confidence'),
            'has_pickswise': game.get('has_pickswise', False),
            'dratings_prob': game.get('home_prob_dratings') if side == 'home' else game.get('away_prob_dratings'),
            'has_dratings': game.get('has_dratings', False),
            # Datos crudos para Fase 6 futura
            'dratings_total_runs': game.get('dratings_total_runs'),
            'dratings_home_runs': game.get('dratings_home_runs'),
            'dratings_away_runs': game.get('dratings_away_runs'),
        })

    picks.sort(key=lambda x: x['confidence'], reverse=True)
    return picks


def suggest_parlays(picks):
    """Sugiere parleys con picks de tier premium/solido/valor."""
    quality_picks = [p for p in picks if p['tier'] in ('premium', 'solido', 'valor')]

    if len(quality_picks) < 3:
        return {}

    parlays = {}

    if len(quality_picks) >= 3:
        legs = quality_picks[:3]
        prob = 1
        for p in legs:
            prob *= (p['model_prob'] / 100)
        parlays['conservador'] = {
            'legs': [{'pick': p['pick'], 'game': p['game'], 'tier': p['tier']} for p in legs],
            'probability': round(prob * 100, 1),
        }

    if len(quality_picks) >= 4:
        legs = quality_picks[:4]
        prob = 1
        for p in legs:
            prob *= (p['model_prob'] / 100)
        parlays['balanceado'] = {
            'legs': [{'pick': p['pick'], 'game': p['game'], 'tier': p['tier']} for p in legs],
            'probability': round(prob * 100, 1),
        }

    if len(quality_picks) >= 6:
        legs = quality_picks[:6]
        prob = 1
        for p in legs:
            prob *= (p['model_prob'] / 100)
        parlays['agresivo'] = {
            'legs': [{'pick': p['pick'], 'game': p['game'], 'tier': p['tier']} for p in legs],
            'probability': round(prob * 100, 1),
        }

    return parlays


if __name__ == '__main__':
    print("Test motor:")
    print(f"  Cuota -132 = {american_odds_to_implied_prob(-132):.1f}% implicita")
    print(f"  60% modelo = cuota ~{implied_prob_to_american_odds(60)}")