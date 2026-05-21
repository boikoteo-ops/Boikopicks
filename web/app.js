const PICKS_URL = './picks.json';

const TIER_LABELS = {
  premium: '🔥 Premium',
  solido:  '⭐ Sólido',
  valor:   '💡 Valor',
  watch:   '👀 Watch'
};

const TIER_ORDER = ['premium', 'solido', 'valor', 'watch'];

let CURRENT_DATA = null;
let CURRENT_FILTER = 'all';

async function loadPicks() {
  try {
    const response = await fetch(PICKS_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    CURRENT_DATA = await response.json();
    render(CURRENT_DATA);
  } catch (e) {
    console.error('Error cargando picks:', e);
    document.getElementById('picksSection').innerHTML =
      `<div class="empty-state">⚠️ No se pudieron cargar los picks.<br><small>${e.message}</small></div>`;
  }
}

function render(data) {
  renderHeader(data);
  renderStats(data);
  renderPicks(data);
  renderParlays(data);
  renderFooter(data);
}

function renderHeader(data) {
  const date = new Date(data.generated_at);
  const weekday = date.toLocaleDateString('es-DO', { weekday: 'long' });
  const day = date.getDate();
  const month = date.toLocaleDateString('es-DO', { month: 'long' });
  const capitalize = s => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  const dateStr = `${capitalize(weekday)}, ${day} de ${month}`;

  document.getElementById('dateText').textContent = dateStr;

  const sports = data.summary?.sports_active || [];
  const sportsStr = sports.length ? sports.join(' · ') : 'Sin juegos';
  document.getElementById('dateMeta').textContent = sportsStr;

  const ageMs = Date.now() - date.getTime();
  const ageHours = ageMs / 1000 / 60 / 60;
  const badge = document.getElementById('liveBadge');
  if (ageHours > 12) {
    badge.classList.add('stale');
    badge.textContent = 'OLD';
  }
}

function renderStats(data) {
  const totalGames = (data.summary?.total_games_mlb || 0) + (data.summary?.total_games_nba || 0);
  const totalPicks = data.summary?.total_picks || (data.picks || []).length;
  const mlPicks = data.summary?.total_picks_ml ?? (data.picks || []).filter(p => p.bet_type !== 'total').length;
  const ouPicks = data.summary?.total_picks_ou ?? (data.picks || []).filter(p => p.bet_type === 'total').length;
  const premium = (data.picks || []).filter(p => p.tier === 'premium').length;

  document.getElementById('statGames').textContent = totalGames;

  // Si hay O/U, mostrar separación clara en segunda línea; si no, número simple
  const statPicksEl = document.getElementById('statPicks');
  if (ouPicks > 0) {
    statPicksEl.innerHTML = `${totalPicks}<span class="stat-breakdown">${mlPicks} ML · ${ouPicks} O/U</span>`;
  } else {
    statPicksEl.textContent = totalPicks;
  }

  document.getElementById('statPremium').textContent = premium;

  // Stats históricas: usar overall por defecto, pero si hay O/U verificados, mostrar tabs
  const stats = data.stats?.overall;
  const mlStats = data.stats?.moneyline?.overall;
  const ouStats = data.stats?.total?.overall;

  if (!stats || stats.verified === 0) {
    document.getElementById('histRecord').textContent = '—';
    document.getElementById('histWinRate').textContent = 'Sin datos aún';
    document.getElementById('histRoi').textContent = '—';
    document.getElementById('histStreak').textContent = '—';
    hideHistTabs();
    return;
  }

  applyHistStats(stats);

  // Mostrar tabs solo si hay O/U verificados
  if (ouStats && ouStats.verified > 0) {
    showHistTabs(stats, mlStats, ouStats);
  } else {
    hideHistTabs();
  }
}

function applyHistStats(stats) {
  const pushesStr = stats.pushes ? `-${stats.pushes}P` : '';
  document.getElementById('histRecord').textContent = `${stats.wins}-${stats.losses}${pushesStr}`;
  document.getElementById('histWinRate').textContent = `${stats.win_rate}% acierto`;

  const roiEl = document.getElementById('histRoi');
  const roiSign = stats.roi >= 0 ? '+' : '';
  roiEl.textContent = `${roiSign}${stats.roi}%`;
  roiEl.className = 'hist-value ' + (stats.roi >= 0 ? 'positive' : 'negative');

  const streakEl = document.getElementById('histStreak');
  if (stats.streak > 0 && stats.streak_type) {
    const letter = stats.streak_type === 'win' ? 'W' : 'L';
    streakEl.textContent = `${stats.streak}${letter}`;
    streakEl.className = 'hist-value ' + (stats.streak_type === 'win' ? 'positive' : 'negative');
  } else {
    streakEl.textContent = '—';
    streakEl.className = 'hist-value';
  }
}

function showHistTabs(allStats, mlStats, ouStats) {
  let tabsEl = document.getElementById('histTabs');
  if (!tabsEl) {
    tabsEl = document.createElement('div');
    tabsEl.id = 'histTabs';
    tabsEl.className = 'hist-tabs';
    tabsEl.innerHTML = `
      <button class="hist-tab active" data-htab="all">Todos</button>
      <button class="hist-tab" data-htab="ml">ML</button>
      <button class="hist-tab" data-htab="ou">O/U</button>
    `;
    const histStrip = document.querySelector('.hist-strip');
    histStrip.parentNode.insertBefore(tabsEl, histStrip);

    tabsEl.addEventListener('click', (e) => {
      if (!e.target.classList.contains('hist-tab')) return;
      tabsEl.querySelectorAll('.hist-tab').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      const which = e.target.dataset.htab;
      if (which === 'ml') applyHistStats(mlStats);
      else if (which === 'ou') applyHistStats(ouStats);
      else applyHistStats(allStats);
    });
  }
}

function hideHistTabs() {
  const tabsEl = document.getElementById('histTabs');
  if (tabsEl) tabsEl.remove();
}

function renderPicks(data) {
  const container = document.getElementById('picksSection');
  let picks = data.picks || [];

  // Filtros: tier OR bet_type
  if (CURRENT_FILTER === 'ml') {
    picks = picks.filter(p => p.bet_type !== 'total');
  } else if (CURRENT_FILTER === 'ou') {
    picks = picks.filter(p => p.bet_type === 'total');
  } else if (CURRENT_FILTER !== 'all') {
    picks = picks.filter(p => p.tier === CURRENT_FILTER);
  }

  if (picks.length === 0) {
    container.innerHTML = '<div class="empty-state">No hay picks que mostrar.</div>';
    return;
  }

  const grouped = {};
  for (const tier of TIER_ORDER) grouped[tier] = [];
  for (const pick of picks) {
    if (grouped[pick.tier]) grouped[pick.tier].push(pick);
  }

  let html = '';
  for (const tier of TIER_ORDER) {
    if (grouped[tier].length === 0) continue;
    if (CURRENT_FILTER === 'all' || CURRENT_FILTER === 'ml' || CURRENT_FILTER === 'ou') {
      html += `<div class="tier-header">${TIER_LABELS[tier]} · ${grouped[tier].length}</div>`;
    }
    for (const pick of grouped[tier]) {
      // Dispatch por bet_type
      if (pick.bet_type === 'total') {
        html += renderOuPickCard(pick);
      } else {
        html += renderPickCard(pick);
      }
    }
  }

  container.innerHTML = html;
}

function renderSourcesBadge(pick) {
  const count = pick.sources_count || 0;
  const total = pick.sources_total || 4;
  const agree = pick.sources_agree;
  const unanimous = pick.sources_unanimous;

  if (count === 0) return '';

  let className = 'sources-badge';
  let label = `${count}/${total}`;

  if (count === 4 && agree === true) {
    className += ' sources-supreme';
    label += ' ✓✓✓';
  } else if (unanimous && count >= 3) {
    className += ' sources-unanimous';
    label += ' ✓✓';
  } else if (agree === true) {
    className += ' sources-agree';
    label += ' ✓';
  } else if (agree === false) {
    className += ' sources-disagree';
    label += ' ⚠';
  } else {
    className += ' sources-partial';
  }

  return `<span class="${className}">${label}</span>`;
}

function renderPickswiseBadge(pick) {
  if (!pick.has_pickswise || !pick.pickswise_confidence) return '';
  const stars = '⭐'.repeat(pick.pickswise_confidence);
  const isBestBet = pick.pickswise_confidence === 5;
  const className = isBestBet ? 'pickswise-badge best-bet' : 'pickswise-badge';
  return `<span class="${className}" title="Pickswise confianza ${pick.pickswise_confidence}/5">${stars}</span>`;
}

function renderDratingsBadge(pick) {
  if (!pick.has_dratings || !pick.dratings_prob) return '';
  return `<span class="dratings-badge" title="DRatings probabilidad">DR ${pick.dratings_prob}%</span>`;
}

function renderPickCard(pick) {
  // ============================================================
  // PICK MONEY LINE (sin cambios respecto al diseño original)
  // ============================================================
  const pickTeamInfo = getTeamInfo(pick.pick);
  const otherTeam = pick.pick === pick.home ? pick.away : pick.home;
  const otherTeamInfo = getTeamInfo(otherTeam);
  const vsText = pick.side === 'home' ? 'vs' : '@';

  const oddsDisplay = pick.estimated_odds > 0 ? `+${pick.estimated_odds}` : `${pick.estimated_odds}`;

  const logoHtml = pickTeamInfo.logo
    ? `<img class="team-logo" src="${pickTeamInfo.logo}" alt="${pickTeamInfo.abbr}" loading="lazy">`
    : `<div class="team-logo" style="background:var(--bg-input);border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">${pickTeamInfo.abbr}</div>`;

  const otherLogoHtml = otherTeamInfo.logo
    ? `<img class="team-logo-mini" src="${otherTeamInfo.logo}" alt="${otherTeamInfo.abbr}" loading="lazy">`
    : `<span style="font-weight:600;">${otherTeamInfo.abbr}</span>`;

  // Formato edge: signo + para positivo, - automático para negativo
  const edgeStr = pick.edge >= 0 ? `+${pick.edge}` : `${pick.edge}`;

  return `
    <div class="pick-card tier-${pick.tier}">
      <div class="pick-header">
        <div class="pick-teams">
          ${logoHtml}
          <div class="pick-team-info">
            <div class="pick-team-name">
              ${pick.pick}
              <span class="bet-badge bet-badge-ml">ML</span>
              <span class="tier-badge tier-${pick.tier}">${pick.tier.toUpperCase()}</span>
            </div>
            <div class="pick-vs">${vsText} ${otherLogoHtml} ${otherTeam} · ${pick.start_time}</div>
          </div>
        </div>
        <div class="pick-odds">${oddsDisplay}</div>
      </div>
      <div class="pick-stats">
        <span class="pick-stat highlight"><strong>${pick.model_prob}%</strong> modelo</span>
        <span class="pick-stat">edge <strong>${edgeStr}%</strong></span>
        <span class="pick-stat">conf <strong>${pick.confidence}</strong></span>
        ${renderPickswiseBadge(pick)}
        ${renderDratingsBadge(pick)}
        ${renderSourcesBadge(pick)}
      </div>
    </div>
  `;
}

function renderOuPickCard(pick) {
  // ============================================================
  // PICK OVER / UNDER (NUEVO)
  // ============================================================
  const homeInfo = getTeamInfo(pick.home);
  const awayInfo = getTeamInfo(pick.away);

  const isOver = pick.side === 'over';
  const arrow = isOver ? '▲' : '▼';
  const sideLabel = isOver ? 'OVER' : 'UNDER';
  const badgeClass = isOver ? 'bet-badge-over' : 'bet-badge-under';

  const awayLogoHtml = awayInfo.logo
    ? `<img class="team-logo-mini" src="${awayInfo.logo}" alt="${awayInfo.abbr}" loading="lazy">`
    : `<span class="team-abbr-mini">${awayInfo.abbr}</span>`;
  const homeLogoHtml = homeInfo.logo
    ? `<img class="team-logo-mini" src="${homeInfo.logo}" alt="${homeInfo.abbr}" loading="lazy">`
    : `<span class="team-abbr-mini">${homeInfo.abbr}</span>`;

  // Odds: si las tiene, mostrar; si no, "-"
  const oddsRaw = pick.odds_american;
  let oddsDisplay = '—';
  if (oddsRaw !== null && oddsRaw !== undefined && oddsRaw !== '') {
    const oddsNum = parseInt(oddsRaw, 10);
    if (!isNaN(oddsNum)) {
      oddsDisplay = oddsNum > 0 ? `+${oddsNum}` : `${oddsNum}`;
    }
  }

  // Líneas por fuente (para mostrar detalle si hay)
  const linesBySource = pick.lines_by_source || {};
  const linesEntries = Object.entries(linesBySource);

  // Sources badge para O/U (count/sources_total con su propia lógica)
  const sourcesBadgeHtml = renderOuSourcesBadge(pick);

  // Warning de divergencia
  const divergenceHtml = pick.lines_diverge
    ? `<div class="lines-diverge-warning">⚠ Las líneas difieren entre fuentes (spread ${pick.lines_spread}). Verifica la línea actual en tu sportsbook.</div>`
    : '';

  // Detalle de fuentes (DR, PW, CV) con sus respectivos picks
  const opinionsHtml = renderOpinionsRow(pick);

  return `
    <div class="pick-card pick-card-ou tier-${pick.tier} ${isOver ? 'is-over' : 'is-under'}">
      <div class="pick-header">
        <div class="pick-teams pick-teams-ou">
          <div class="pick-teams-matchup">
            ${awayLogoHtml}
            <span class="ou-vs">@</span>
            ${homeLogoHtml}
          </div>
          <div class="pick-team-info">
            <div class="pick-team-name">
              <span class="bet-badge ${badgeClass}">${arrow} ${sideLabel} ${pick.line ?? '—'}</span>
              <span class="tier-badge tier-${pick.tier}">${pick.tier.toUpperCase()}</span>
            </div>
            <div class="pick-vs">${pick.away} @ ${pick.home} · ${pick.start_time}</div>
          </div>
        </div>
        <div class="pick-odds pick-odds-ou">${oddsDisplay}</div>
      </div>
      <div class="pick-stats">
        <span class="pick-stat">conf <strong>${pick.confidence}</strong></span>
        ${opinionsHtml}
        ${sourcesBadgeHtml}
      </div>
      ${divergenceHtml}
    </div>
  `;
}

function renderOuSourcesBadge(pick) {
  const count = pick.sources_count || 0;
  const total = pick.sources_total || 3;
  const agreeCount = pick.agree_count || 0;
  const unanimous = pick.sources_unanimous;

  if (count === 0) return '';

  let className = 'sources-badge sources-badge-ou';
  let label = `${agreeCount}/${count}`;

  if (count === 3 && unanimous) {
    className += ' sources-unanimous';
    label += ' ✓✓';
  } else if (count >= 2 && agreeCount === count) {
    className += ' sources-agree';
    label += ' ✓';
  } else if (count > 1 && agreeCount < count) {
    className += ' sources-partial';
  }

  return `<span class="${className}">${label}</span>`;
}

function renderOpinionsRow(pick) {
  // Muestra los picks individuales de cada fuente: DR, PW, CV
  const opinions = pick.opinions || [];
  if (opinions.length === 0) return '';

  const shortName = {
    'dratings': 'DR',
    'pickswise': 'PW',
    'covers': 'CV'
  };

  const items = opinions.map(op => {
    const short = shortName[op.source] || op.source.slice(0, 2).toUpperCase();
    const symbol = op.pick === 'over' ? '↑' : '↓';
    const cls = op.pick === 'over' ? 'op-over' : 'op-under';
    return `<span class="opinion-chip ${cls}">${short} ${symbol}</span>`;
  }).join('');

  return `<span class="opinions-row">${items}</span>`;
}

function renderParlays(data) {
  const container = document.getElementById('parlaysSection');
  const parlays = data.parlays || {};
  const keys = Object.keys(parlays);
  if (keys.length === 0) {
    container.innerHTML = '';
    return;
  }

  let html = '<div class="parlays-title">Parleys sugeridos</div>';
  for (const name of keys) {
    const parlay = parlays[name];
    const legsHtml = parlay.legs.map(leg => {
      const info = getTeamInfo(leg.pick);
      const logo = info.logo
        ? `<img class="team-logo-mini" src="${info.logo}" alt="" loading="lazy">`
        : '';
      return `<div class="parlay-leg">${logo}<span>${leg.pick}</span></div>`;
    }).join('');

    html += `
      <div class="parlay-card">
        <div class="parlay-header">
          <div class="parlay-name">${name} · ${parlay.legs.length} patas</div>
          <div class="parlay-prob">${parlay.probability}%</div>
        </div>
        <div class="parlay-legs">${legsHtml}</div>
      </div>
    `;
  }
  container.innerHTML = html;
}

function renderFooter(data) {
  const date = new Date(data.generated_at);
  const timeStr = date.toLocaleString('es-DO', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
  document.getElementById('lastUpdate').textContent = `Última actualización: ${timeStr}`;
}

document.addEventListener('click', (e) => {
  if (e.target.classList.contains('filter-btn')) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    CURRENT_FILTER = e.target.dataset.filter;
    if (CURRENT_DATA) renderPicks(CURRENT_DATA);
  }
});

loadPicks();
