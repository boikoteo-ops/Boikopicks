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
  const premium = (data.picks || []).filter(p => p.tier === 'premium').length;

  document.getElementById('statGames').textContent = totalGames;
  document.getElementById('statPicks').textContent = totalPicks;
  document.getElementById('statPremium').textContent = premium;

  const stats = data.stats?.overall;
  if (!stats || stats.verified === 0) {
    document.getElementById('histRecord').textContent = '—';
    document.getElementById('histWinRate').textContent = 'Sin datos aún';
    document.getElementById('histRoi').textContent = '—';
    document.getElementById('histStreak').textContent = '—';
    return;
  }

  document.getElementById('histRecord').textContent = `${stats.wins}-${stats.losses}`;
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

function renderPicks(data) {
  const container = document.getElementById('picksSection');
  let picks = data.picks || [];

  if (CURRENT_FILTER !== 'all') {
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
    if (CURRENT_FILTER === 'all') {
      html += `<div class="tier-header">${TIER_LABELS[tier]} · ${grouped[tier].length}</div>`;
    }
    for (const pick of grouped[tier]) {
      html += renderPickCard(pick);
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

  // 4/4 con acuerdo total: nivel maximo
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

  return `
    <div class="pick-card tier-${pick.tier}">
      <div class="pick-header">
        <div class="pick-teams">
          ${logoHtml}
          <div class="pick-team-info">
            <div class="pick-team-name">
              ${pick.pick}
              <span class="tier-badge tier-${pick.tier}">${pick.tier.toUpperCase()}</span>
            </div>
            <div class="pick-vs">${vsText} ${otherLogoHtml} ${otherTeam} · ${pick.start_time}</div>
          </div>
        </div>
        <div class="pick-odds">${oddsDisplay}</div>
      </div>
      <div class="pick-stats">
        <span class="pick-stat highlight"><strong>${pick.model_prob}%</strong> modelo</span>
        <span class="pick-stat">edge <strong>+${pick.edge}%</strong></span>
        <span class="pick-stat">conf <strong>${pick.confidence}</strong></span>
        ${renderPickswiseBadge(pick)}
        ${renderDratingsBadge(pick)}
        ${renderSourcesBadge(pick)}
      </div>
    </div>
  `;
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