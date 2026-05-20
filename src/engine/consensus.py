"""
Motor de consenso: combina schedule + numberFire + Covers + Pickswise + DRatings.
Genera picks con score de confianza y acuerdo entre fuentes.

Incluye logica paralela para Over/Under (Fase 6):
- merge_ou_data() : cruza datos O/U de DRatings + Pickswise + Covers
- generate_ou_picks() : genera picks O/U clasificados por tier
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
            'bet_type': 'moneyline',
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


# ===========================================================================
# OVER / UNDER (Fase 6 — totales)
# ===========================================================================

def _line_to_key(line):
    """Convierte una linea (8.5, 9.0, etc.) a string para comparar."""
    return f"{line:.2f}" if line is not None else "?"


def merge_ou_data(schedule_games, dratings_predictions=None,
                  pickswise_totals=None, covers_totals=None):
    """
    Cruza datos O/U de las 3 fuentes (DRatings, Pickswise Totals, Covers Totals)
    contra el schedule. Devuelve lista de juegos enriquecidos con info O/U.

    NOTA: DRatings reusa sus dicts existentes (que ya tienen ou_pick, ou_line,
    etc. desde Fase 1). Pickswise y Covers vienen de sus nuevas funciones
    get_pickswise_totals() y get_covers_totals().
    """
    if dratings_predictions is None:
        dratings_predictions = []
    if pickswise_totals is None:
        pickswise_totals = []
    if covers_totals is None:
        covers_totals = []

    merged = []

    for game in schedule_games:
        enriched = {
            'sport': game.get('sport'),
            'home': game.get('home'),
            'away': game.get('away'),
            'start_time': game.get('start_time', 'TBD'),
            # DRatings O/U
            'has_dratings_ou': False,
            'dratings_ou_pick': None,
            'dratings_ou_line': None,
            'dratings_ou_diff': None,
            'dratings_total_runs': None,
            'dratings_ou_book': None,
            'dratings_ou_over_odds': None,
            'dratings_ou_under_odds': None,
            # Pickswise O/U
            'has_pickswise_ou': False,
            'pickswise_ou_pick': None,
            'pickswise_ou_line': None,
            'pickswise_ou_confidence': None,
            'pickswise_ou_odds': None,
            # Covers O/U
            'has_covers_ou': False,
            'covers_ou_pick': None,
            'covers_ou_line': None,
            'covers_ou_pct_over': None,
            'covers_ou_pct_under': None,
        }

        # === DRatings ===
        for pred in dratings_predictions:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                # DRatings puede traer ou_pick=None (PASS, demasiado cerca de la linea)
                if pred.get('ou_line') is not None:
                    enriched['has_dratings_ou'] = True
                    enriched['dratings_ou_pick'] = pred.get('ou_pick')  # 'over'|'under'|None (PASS)
                    enriched['dratings_ou_line'] = pred.get('ou_line')
                    enriched['dratings_ou_diff'] = pred.get('ou_diff')
                    enriched['dratings_total_runs'] = pred.get('total_runs')
                    enriched['dratings_ou_book'] = pred.get('ou_book')
                    enriched['dratings_ou_over_odds'] = pred.get('ou_over_odds')
                    enriched['dratings_ou_under_odds'] = pred.get('ou_under_odds')
                break

        # === Pickswise ===
        for pred in pickswise_totals:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['has_pickswise_ou'] = True
                enriched['pickswise_ou_pick'] = pred.get('ou_pick')
                enriched['pickswise_ou_line'] = pred.get('ou_line')
                enriched['pickswise_ou_confidence'] = pred.get('ou_confidence')
                enriched['pickswise_ou_odds'] = pred.get('ou_odds_american')
                break

        # === Covers ===
        for pred in covers_totals:
            if (_teams_match(game['home'], pred['home']) and
                _teams_match(game['away'], pred['away'])):
                enriched['has_covers_ou'] = True
                enriched['covers_ou_pick'] = pred.get('ou_pick')
                enriched['covers_ou_line'] = pred.get('ou_line')
                enriched['covers_ou_pct_over'] = pred.get('ou_pct_over')
                enriched['covers_ou_pct_under'] = pred.get('ou_pct_under')
                break

        # === Calcular consenso (Decisión 1: adaptativo — solo cuentan fuentes que opinan) ===
        opinions = []  # lista de ('over'|'under', source_name)

        # DRatings cuenta solo si dio un pick (no PASS)
        if enriched['has_dratings_ou'] and enriched['dratings_ou_pick'] in ('over', 'under'):
            opinions.append((enriched['dratings_ou_pick'], 'dratings'))

        if enriched['has_pickswise_ou'] and enriched['pickswise_ou_pick'] in ('over', 'under'):
            opinions.append((enriched['pickswise_ou_pick'], 'pickswise'))

        if enriched['has_covers_ou'] and enriched['covers_ou_pick'] in ('over', 'under'):
            opinions.append((enriched['covers_ou_pick'], 'covers'))

        enriched['ou_sources_count'] = len(opinions)
        enriched['ou_sources_total'] = 3
        enriched['ou_opinions'] = opinions

        if len(opinions) == 0:
            enriched['ou_consensus_pick'] = None
            enriched['ou_agree_count'] = 0
            enriched['ou_sources_agree'] = None
            enriched['ou_sources_unanimous'] = False
        else:
            overs = sum(1 for p, _ in opinions if p == 'over')
            unders = sum(1 for p, _ in opinions if p == 'under')
            if overs > unders:
                enriched['ou_consensus_pick'] = 'over'
                enriched['ou_agree_count'] = overs
            elif unders > overs:
                enriched['ou_consensus_pick'] = 'under'
                enriched['ou_agree_count'] = unders
            else:
                # Empate (2/2 raro pero posible: 1 over, 1 under)
                enriched['ou_consensus_pick'] = None
                enriched['ou_agree_count'] = 1  # nadie gana
            enriched['ou_sources_agree'] = (enriched['ou_agree_count'] == len(opinions)
                                            and len(opinions) >= 2)
            enriched['ou_sources_unanimous'] = (enriched['ou_sources_agree']
                                                and len(opinions) >= 3)

        # === Líneas (Decisión 3: mostrar todas y advertir si divergen) ===
        lines_available = []
        if enriched['dratings_ou_line'] is not None:
            lines_available.append(('dratings', enriched['dratings_ou_line']))
        if enriched['pickswise_ou_line'] is not None:
            lines_available.append(('pickswise', enriched['pickswise_ou_line']))
        if enriched['covers_ou_line'] is not None:
            lines_available.append(('covers', enriched['covers_ou_line']))

        enriched['ou_lines_by_source'] = dict(lines_available)

        # Linea "principal" para mostrar: preferir Covers > DRatings > Pickswise
        principal_line = None
        for src in ('covers', 'dratings', 'pickswise'):
            if src in enriched['ou_lines_by_source']:
                principal_line = enriched['ou_lines_by_source'][src]
                break
        enriched['ou_principal_line'] = principal_line

        # Detectar divergencia significativa entre lineas
        if len(lines_available) >= 2:
            values = [v for _, v in lines_available]
            spread = max(values) - min(values)
            enriched['ou_lines_spread'] = round(spread, 2)
            enriched['ou_lines_diverge'] = spread > 0.5  # umbral arbitrario
        else:
            enriched['ou_lines_spread'] = 0
            enriched['ou_lines_diverge'] = False

        merged.append(enriched)

    return merged


def generate_ou_picks(games):
    """
    Genera picks O/U clasificados por tier.

    Reusa los nombres de tiers de ML (Premium/Solido/Valor/Watch).
    Criterio de tier basado en:
      - cuantas fuentes acuerdan (1/1 vs 2/2 vs 3/3)
      - magnitud de la diferencia de DRatings (si esta disponible)
      - porcentaje de Covers (si la mayoria publica esta convencida)
    """
    picks = []

    for game in games:
        consensus_pick = game.get('ou_consensus_pick')
        sources_count = game.get('ou_sources_count', 0)

        # Filtro minimo: al menos 1 opinion y un pick definido
        if not consensus_pick or sources_count == 0:
            continue

        agree_count = game.get('ou_agree_count', 0)
        sources_agree = game.get('ou_sources_agree')
        sources_unanimous = game.get('ou_sources_unanimous', False)

        # === Calcular confianza base ===
        # Score base: 25 puntos solo por tener consenso
        confidence = 25.0

        # Bonus por acuerdo unanime (cuantas fuentes coinciden)
        if sources_count == 1:
            confidence += 0   # solo 1 opinion, sin bonus
        elif sources_count == 2 and agree_count == 2:
            confidence += 12  # 2/2 acuerdo
        elif sources_count == 3 and agree_count == 3:
            confidence += 25  # 3/3 unanimo
        elif sources_count == 3 and agree_count == 2:
            confidence += 5   # 2/3 (un disenso)

        # Bonus por magnitud de DRatings (si la fuente opina)
        dratings_diff = game.get('dratings_ou_diff')
        if dratings_diff is not None:
            diff_abs = abs(dratings_diff)
            # diff de 0.5 carreras o mas es senal fuerte
            if diff_abs >= 0.5:
                confidence += 8
            elif diff_abs >= 0.3:
                confidence += 4

        # Bonus por convicción del público (Covers): si >65% del lado pickeado
        covers_pct_over = game.get('covers_ou_pct_over')
        covers_pct_under = game.get('covers_ou_pct_under')
        if consensus_pick == 'over' and covers_pct_over and covers_pct_over >= 65:
            confidence += 5
        elif consensus_pick == 'under' and covers_pct_under and covers_pct_under >= 65:
            confidence += 5

        # Penalizacion: lineas divergen significativamente entre fuentes
        if game.get('ou_lines_diverge'):
            confidence -= 6

        confidence = max(0, min(100, round(confidence, 1)))

        # === Asignar tier basado en sources_count + agree + confidence ===
        if sources_count == 3 and agree_count == 3 and confidence >= 50:
            tier = 'premium'
            tier_label = 'Premium'
        elif sources_count >= 2 and agree_count == sources_count and confidence >= 40:
            tier = 'solido'
            tier_label = 'Solido'
        elif agree_count >= 2 and confidence >= 30:
            tier = 'valor'
            tier_label = 'Valor'
        else:
            tier = 'watch'
            tier_label = 'Watch'

        # === Lineas: principal + todas las disponibles ===
        principal_line = game.get('ou_principal_line')
        lines_by_source = game.get('ou_lines_by_source', {})

        # === Odds principales: del lado pickeado, preferir DRatings ===
        principal_odds = None
        if consensus_pick == 'over':
            principal_odds = game.get('dratings_ou_over_odds')
        else:
            principal_odds = game.get('dratings_ou_under_odds')

        picks.append({
            'bet_type': 'total',
            'sport': game['sport'],
            'game': f"{game['away']} @ {game['home']}",
            'home': game['home'],
            'away': game['away'],
            'pick': consensus_pick.upper(),  # 'OVER' o 'UNDER'
            'side': consensus_pick,           # 'over' o 'under'
            'line': principal_line,
            'start_time': game.get('start_time', 'TBD'),
            'confidence': confidence,
            'tier': tier,
            'tier_label': tier_label,
            'odds_american': principal_odds,
            # Consenso
            'sources_count': sources_count,
            'sources_total': 3,
            'sources_agree': sources_agree,
            'sources_unanimous': sources_unanimous,
            'agree_count': agree_count,
            'opinions': [{'source': src, 'pick': pk} for pk, src in game.get('ou_opinions', [])],
            # Detalle por fuente
            'dratings_pick': game.get('dratings_ou_pick'),
            'dratings_line': game.get('dratings_ou_line'),
            'dratings_diff': game.get('dratings_ou_diff'),
            'dratings_proj': game.get('dratings_total_runs'),
            'pickswise_pick': game.get('pickswise_ou_pick'),
            'pickswise_line': game.get('pickswise_ou_line'),
            'pickswise_confidence': game.get('pickswise_ou_confidence'),
            'covers_pick': game.get('covers_ou_pick'),
            'covers_line': game.get('covers_ou_line'),
            'covers_pct_over': game.get('covers_ou_pct_over'),
            'covers_pct_under': game.get('covers_ou_pct_under'),
            # Lineas y advertencia
            'lines_by_source': lines_by_source,
            'lines_spread': game.get('ou_lines_spread', 0),
            'lines_diverge': game.get('ou_lines_diverge', False),
        })

    picks.sort(key=lambda x: x['confidence'], reverse=True)
    return picks


if __name__ == '__main__':
    print("Test motor:")
    print(f"  Cuota -132 = {american_odds_to_implied_prob(-132):.1f}% implicita")
    print(f"  60% modelo = cuota ~{implied_prob_to_american_odds(60)}")
