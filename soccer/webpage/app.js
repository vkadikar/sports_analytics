/**
 * The Gentlemen's Invitational: Fantasy Prem (2026-27)
 * Frontend Application Logic & Multi-Page Router
 * Fully Connected to Live Fantrax API & Official Real League Dataset
 */

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

// Global Application State
const APP_STATE = {
  activePage: 'dashboard',
  activeGameweek: 1,
  matchupFilter: 'all',
  sorts: {
    'table-official-standings': { key: 'rank', dir: 'asc' },
    'table-lineup-efficiency': { key: 'rank', dir: 'asc' },
    'table-optimal-standings': { key: 'rank', dir: 'asc' },
    'table-median-standings': { key: 'rank', dir: 'asc' },
    'table-career-prizes': { key: 'careerMoney', dir: 'desc' }
  }
};

function initApp() {
  const initGw = LEAGUE_DATA.currentSeason.currentGameweek || 1;
  APP_STATE.activeGameweek = initGw;

  setupTableSortListeners();
  populateGameweekDropdown();

  // Render Initial Active Page
  navigateToPage('dashboard');
}

// 1. Page Router Navigation
function navigateToPage(pageId) {
  APP_STATE.activePage = pageId;

  // Update Navigation Bar State
  document.querySelectorAll(".main-nav .nav-link").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-page") === pageId);
  });

  // Update Page View Visibility
  document.querySelectorAll(".page-view").forEach(view => {
    view.classList.toggle("active", view.id === `page-${pageId}`);
  });

  // Scroll to Top Smoothly
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Render Page Content
  if (pageId === 'dashboard') {
    renderDashboard();
  } else if (pageId === 'standings') {
    renderOfficialStandings();
    renderOptimalStandings();
    renderMedianStandings();
    renderManagerEfficiency();
  } else if (pageId === 'matchups') {
    renderMatchupCenter(APP_STATE.activeGameweek, APP_STATE.matchupFilter);
    renderH2HMatrix();
  } else if (pageId === 'tournaments') {
    renderChampionsLeague();
    renderLingineniCup();
  } else if (pageId === 'history') {
    renderManagerDossiers();
    renderHallOfFame();
    renderCareerPrizeMoney();
  } else if (pageId === 'rules') {
    renderPrizePool();
    initIhopCalculator();
    renderScoringMatrix("D");
    renderBylawsAccordion();
  }
}

// 2. Executive Dashboard Overview
function renderDashboard() {
  // Pulse Metric Widgets
  const pulseGrid = document.getElementById("dashboard-pulse-grid");
  if (pulseGrid) {
    const standings = LEAGUE_DATA.currentSeason.officialStandings || [];
    const leader = standings[0] || { manager: 'Varun Kadikar', team: 'FC VAR', pts: 6 };
    const lastPlace = standings[standings.length - 1] || { manager: 'Subba Duvuuru', team: 'sduvuuru', pts: 0 };
    const highScorer = LEAGUE_DATA.currentSeason.weeklyHighScores[1] || { manager: 'Nilay Agarwalla', score: 142.50 };

    pulseGrid.innerHTML = `
      <div class="pulse-card">
        <div class="pulse-lbl">League Leader</div>
        <div class="pulse-val" style="color: var(--pl-green);">${leader.team}</div>
        <div class="pulse-sub">${leader.manager} • ${leader.pts} Pts (${leader.w}-${leader.d}-${leader.l})</div>
      </div>
      <div class="pulse-card">
        <div class="pulse-lbl">Weekly High Scorer</div>
        <div class="pulse-val" style="color: #fbbf24;">${highScorer.score.toFixed(1)} Pts</div>
        <div class="pulse-sub">${highScorer.manager} • $10 Purse Prize</div>
      </div>
      <div class="pulse-card">
        <div class="pulse-lbl">Total Purse Pool</div>
        <div class="pulse-val" style="color: var(--pl-cyan);">$1,400</div>
        <div class="pulse-sub">14 Competitors • 6 Cities</div>
      </div>
      <div class="pulse-card">
        <div class="pulse-lbl">IHOP Gauntlet Danger Zone</div>
        <div class="pulse-val" style="color: #f87171;">${lastPlace.team}</div>
        <div class="pulse-sub">14th Rank • ${lastPlace.manager} (24h Penalty)</div>
      </div>
    `;
  }

  // Dashboard Standings Snapshot
  const tbody = document.getElementById("dashboard-standings-tbody");
  if (tbody) {
    const standings = LEAGUE_DATA.currentSeason.officialStandings || [];
    tbody.innerHTML = standings.slice(0, 14).map((row, idx) => {
      const isCl = idx < 6;
      const isIhop = idx === 13;
      let posBadge = `<span style="font-weight: 700;">${idx + 1}</span>`;
      if (isCl) posBadge += ` <span style="font-size:0.7rem; color:var(--pl-cyan);" title="CL Qualified">⭐</span>`;
      if (isIhop) posBadge += ` <span style="font-size:0.7rem; color:#f87171;" title="IHOP Penalty Zone">🥞</span>`;

      return `
        <tr style="${isCl ? 'background: rgba(6, 182, 212, 0.04);' : isIhop ? 'background: rgba(239, 68, 68, 0.06);' : ''}">
          <td>${posBadge}</td>
          <td>
            <div style="font-weight: 700; color: var(--text-main);">${row.team}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${row.manager}</div>
          </td>
          <td>${row.p}</td>
          <td style="color: var(--pl-green); font-weight: 700;">${row.w}</td>
          <td>${row.d}</td>
          <td style="color: #f87171;">${row.l}</td>
          <td style="font-weight: 800; color: var(--text-highlight);">${row.pts}</td>
        </tr>
      `;
    }).join("");
  }

  // Active Matchday Fixtures
  const matchupsList = document.getElementById("dashboard-matchups-list");
  if (matchupsList) {
    const gw = APP_STATE.activeGameweek || 1;
    const title = document.getElementById("dashboard-matchday-title");
    if (title) title.textContent = `⚽ Matchweek ${gw} Fixtures`;

    const fixtures = (LEAGUE_DATA.currentSeason.gameweekMatchups[gw] || []).slice(0, 4);
    matchupsList.innerHTML = fixtures.map(m => renderMatchCard(m)).join("");
  }
}

// 3. Sub-View Switches
function switchStandingsSubView(viewId) {
  document.querySelectorAll("#standings-subnav .sub-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  document.querySelectorAll(".standings-view").forEach(view => {
    view.style.display = (view.id === `view-${viewId}`) ? "block" : "none";
  });
}

function switchTournamentSubView(viewId) {
  document.querySelectorAll("#page-tournaments .sub-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  const clView = document.getElementById("tourney-view-cl");
  const cupView = document.getElementById("tourney-view-cup");
  if (clView) clView.style.display = (viewId === 'cl') ? "block" : "none";
  if (cupView) cupView.style.display = (viewId === 'cup') ? "block" : "none";
}

function switchHistorySubView(viewId) {
  document.querySelectorAll("#page-history .sub-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  document.getElementById("history-view-dossiers").style.display = (viewId === 'dossiers') ? "block" : "none";
  document.getElementById("history-view-hall-of-fame").style.display = (viewId === 'hall-of-fame') ? "block" : "none";
  document.getElementById("history-view-prize-money").style.display = (viewId === 'prize-money') ? "block" : "none";
}

function switchRulesSubView(viewId) {
  document.querySelectorAll("#page-rules .sub-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  document.getElementById("rules-view-prizes").style.display = (viewId === 'prizes') ? "block" : "none";
  document.getElementById("rules-view-ihop").style.display = (viewId === 'ihop') ? "block" : "none";
  document.getElementById("rules-view-scoring").style.display = (viewId === 'scoring') ? "block" : "none";
  document.getElementById("rules-view-bylaws").style.display = (viewId === 'bylaws') ? "block" : "none";
}

// 4. Render Official Standings Table
function renderOfficialStandings() {
  const tbody = document.getElementById("official-standings-tbody");
  if (!tbody) return;

  let standings = [...(LEAGUE_DATA.currentSeason.officialStandings || [])];
  const sort = APP_STATE.sorts['table-official-standings'];
  if (sort) {
    sortDataArray(standings, sort.key, sort.dir, sort.type || 'num');
  }

  tbody.innerHTML = standings.map((row, idx) => {
    const isCl = row.rank <= 6;
    const isIhop = row.rank === 14;

    const formHtml = (row.form || []).map(f => `<span class="form-badge form-${f.toLowerCase()}">${f}</span>`).join("");
    let diffStr = row.diff > 0 ? `+${row.diff.toFixed(1)}` : row.diff.toFixed(1);

    return `
      <tr style="${isCl ? 'background: rgba(6, 182, 212, 0.04);' : isIhop ? 'background: rgba(239, 68, 68, 0.06);' : ''}">
        <td style="font-weight: 800; color: ${isCl ? 'var(--pl-cyan)' : isIhop ? '#f87171' : 'var(--text-main)'};">
          ${row.rank} ${isCl ? '⭐' : isIhop ? '🥞' : ''}
        </td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${row.team}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${row.manager}</div>
        </td>
        <td>${row.p}</td>
        <td style="color: var(--pl-green); font-weight: 700;">${row.w}</td>
        <td>${row.d}</td>
        <td style="color: #f87171;">${row.l}</td>
        <td>${row.pf.toFixed(1)}</td>
        <td>${row.pa.toFixed(1)}</td>
        <td style="color: ${row.diff >= 0 ? 'var(--pl-green)' : '#f87171'}; font-weight: 600;">${diffStr}</td>
        <td style="font-weight: 800; font-size: 1.05rem; color: var(--text-highlight);">${row.pts}</td>
        <td>${formHtml}</td>
        <td style="color: var(--pl-cyan); font-weight: 700;">${row.maxPf ? row.maxPf.toFixed(1) : '—'}</td>
        <td style="font-weight: 700; color: ${row.eff >= 95 ? 'var(--pl-green)' : 'inherit'};">${row.eff ? row.eff.toFixed(1) + '%' : '—'}</td>
      </tr>
    `;
  }).join("");
}

// 5. Render Optimal Standings Table
function renderOptimalStandings() {
  const tbody = document.getElementById("optimal-standings-tbody");
  if (!tbody) return;

  let standings = [...(LEAGUE_DATA.currentSeason.optimalStandings || [])];
  const sort = APP_STATE.sorts['table-optimal-standings'];
  if (sort) {
    sortDataArray(standings, sort.key, sort.dir, sort.type || 'num');
  }

  tbody.innerHTML = standings.map(row => {
    let shiftBadge = `<span style="color: var(--text-muted);">—</span>`;
    if (row.rankShift > 0) shiftBadge = `<span style="color: var(--pl-green); font-weight: 700;">▲ +${row.rankShift}</span>`;
    else if (row.rankShift < 0) shiftBadge = `<span style="color: #f87171; font-weight: 700;">▼ ${row.rankShift}</span>`;

    return `
      <tr>
        <td style="font-weight: 800; color: var(--pl-cyan);">${row.rank}</td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${row.team}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${row.manager}</div>
        </td>
        <td>${row.p}</td>
        <td style="color: var(--pl-green); font-weight: 700;">${row.w}</td>
        <td>${row.d}</td>
        <td style="color: #f87171;">${row.l}</td>
        <td style="font-weight: 700; color: var(--pl-cyan);">${row.optPf.toFixed(1)}</td>
        <td>${row.optPa.toFixed(1)}</td>
        <td style="color: #f87171; font-weight: 700;">-${row.benchPoints.toFixed(1)}</td>
        <td style="font-weight: 800; font-size: 1.05rem; color: var(--text-highlight);">${row.pts}</td>
        <td>${row.actualRank}</td>
        <td>${shiftBadge}</td>
        <td style="color: ${row.ptsGain >= 0 ? 'var(--pl-green)' : '#f87171'}; font-weight: 700;">+${row.ptsGain} Pts</td>
      </tr>
    `;
  }).join("");
}

// 6. Render Standings vs Median Table
function renderMedianStandings() {
  const tbody = document.getElementById("median-tbody");
  if (!tbody) return;

  let standings = [...(LEAGUE_DATA.currentSeason.standingsVsMedian || [])];
  const sort = APP_STATE.sorts['table-median-standings'];
  if (sort) {
    sortDataArray(standings, sort.key, sort.dir, sort.type || 'num');
  }

  tbody.innerHTML = standings.map(row => {
    return `
      <tr>
        <td style="font-weight: 800; color: var(--pl-green);">${row.rank}</td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${row.team}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${row.manager}</div>
        </td>
        <td style="font-weight: 700;">${row.medianWins}-${row.medianLosses}-${row.medianDraws}</td>
        <td style="font-weight: 800; font-size: 1.05rem; color: var(--text-highlight);">${row.pts}</td>
        <td>${row.pf.toFixed(1)}</td>
        <td>${row.pa.toFixed(1)}</td>
        <td>${row.actualRecord}</td>
        <td style="font-weight: 600; color: ${row.luckFactor.includes('Unlucky') ? '#f87171' : 'var(--pl-green)'};">${row.luckFactor}</td>
      </tr>
    `;
  }).join("");
}

// 7. Render Lineup Efficiency Table
function renderManagerEfficiency() {
  const tbody = document.getElementById("lineup-efficiency-tbody");
  if (!tbody) return;

  let standings = [...(LEAGUE_DATA.currentSeason.managerEfficiency || [])];
  const sort = APP_STATE.sorts['table-lineup-efficiency'];
  if (sort) {
    sortDataArray(standings, sort.key, sort.dir, sort.type || 'num');
  }

  tbody.innerHTML = standings.map(row => {
    return `
      <tr>
        <td style="font-weight: 800; color: var(--pl-green);">${row.rank}</td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${row.manager}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${row.team}</div>
        </td>
        <td>${row.actualAvg.toFixed(2)}</td>
        <td>${row.optAvg.toFixed(2)}</td>
        <td style="color: #f87171;">-${row.missedAvg.toFixed(2)}</td>
        <td style="color: #f87171; font-weight: 700;">-${row.missedTotal.toFixed(1)}</td>
        <td style="font-weight: 800; font-size: 1.05rem; color: ${row.efficiencyPct >= 95 ? 'var(--pl-green)' : 'var(--text-highlight)'};">${row.efficiencyPct.toFixed(1)}%</td>
      </tr>
    `;
  }).join("");
}

// 8. Matchup Center
function jumpToGameweek(gw) {
  APP_STATE.activeGameweek = gw;
  APP_STATE.matchupFilter = 'all';
  const select = document.getElementById("gw-selector-dropdown");
  if (select) select.value = gw;
  document.querySelectorAll("#matchup-filter-group .fixture-filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-filter") === 'all');
  });
  renderMatchupCenter(gw, 'all');
}

function filterMatchups(filterType) {
  APP_STATE.matchupFilter = filterType;
  document.querySelectorAll("#matchup-filter-group .fixture-filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-filter") === filterType);
  });
  renderMatchupCenter(APP_STATE.activeGameweek, filterType);
}

function renderMatchupCenter(gameweek = 1, filterType = 'all') {
  APP_STATE.activeGameweek = gameweek;
  const container = document.getElementById("matchups-grid");
  const gwTitle = document.getElementById("matchup-gw-title");
  const select = document.getElementById("gw-selector-dropdown");
  if (!container) return;

  if (select && parseInt(select.value) !== gameweek) {
    select.value = gameweek;
  }

  const completedGws = LEAGUE_DATA.currentSeason.completedGameweeks || [1];

  // Champions League View
  if (filterType === 'champions_league') {
    if (gwTitle) {
      gwTitle.innerHTML = `⭐ 2026-27 Champions League Tournament Schedule <span style="font-size: 0.85rem; color: var(--pl-cyan); font-weight: 600;">(GW 6, 11, 16, 21, 26, 31, 33, 36)</span>`;
    }

    const clGws = [6, 11, 16, 21, 26, 31, 33, 36];
    let html = "";

    clGws.forEach(gwNum => {
      const isGwCompleted = completedGws.includes(gwNum);
      const gwFixtures = (LEAGUE_DATA.currentSeason.gameweekMatchups[gwNum] || []).filter(f => f.competition === 'champions_league' || f.isConcurrentCL);

      let stageName = `Gameweek ${gwNum}`;
      if (gwNum === 6) stageName = `Gameweek 6 • Group Stage (Matchday 1)`;
      else if (gwNum === 11) stageName = `Gameweek 11 • Group Stage (Matchday 2)`;
      else if (gwNum === 16) stageName = `Gameweek 16 • Group Stage (Matchday 3)`;
      else if (gwNum === 21) stageName = `Gameweek 21 • Group Stage (Matchday 4)`;
      else if (gwNum === 26) stageName = `Gameweek 26 • Group Stage (Matchday 5)`;
      else if (gwNum === 31) stageName = `Gameweek 31 • Semi-Finals (Leg 1)`;
      else if (gwNum === 33) stageName = `Gameweek 33 • Semi-Finals (Leg 2)`;
      else if (gwNum === 36) stageName = `Gameweek 36 • Champions League Final 🏆`;

      html += `
        <div class="tournament-stage-header" style="color: var(--pl-cyan); grid-column: 1 / -1; font-weight: 800; font-size: 1.05rem; margin-top: 16px; border-bottom: 1px solid var(--border-glass); padding-bottom: 4px;">
          <span>⭐ ${stageName}</span>
          <span style="font-size: 0.75rem; font-weight: 600; color: var(--text-muted); float: right;">${isGwCompleted ? '✓ Completed' : '• Scheduled'}</span>
        </div>
      `;

      if (gwFixtures.length === 0) {
        html += `
          <div class="matchup-card card-cl" style="grid-column: 1 / -1; text-align: center; padding: 16px;">
            <div style="font-size: 0.85rem; color: var(--text-muted);">Fixtures scheduled for ${stageName}</div>
          </div>
        `;
      } else {
        html += gwFixtures.map(m => renderMatchCard(m)).join("");
      }
    });

    container.innerHTML = html;
    return;
  }

  // Lingineni Cup View
  if (filterType === 'lingineni_cup') {
    if (gwTitle) {
      gwTitle.innerHTML = `🏆 2026-27 Lingineni Cup Knockout Bracket & Schedule <span style="font-size: 0.85rem; color: #fbbf24; font-weight: 600;">(GW 9, 14, 19, 24, 29, 34)</span>`;
    }

    const cupGws = [9, 14, 19, 24, 29, 34];
    let html = "";

    cupGws.forEach(gwNum => {
      const isGwCompleted = completedGws.includes(gwNum);
      const gwFixtures = (LEAGUE_DATA.currentSeason.gameweekMatchups[gwNum] || []).filter(f => f.competition === 'lingineni_cup');

      let stageName = `Gameweek ${gwNum}`;
      if (gwNum === 9) stageName = `Gameweek 9 • Round 1 (Bottom 4 Qualifier)`;
      else if (gwNum === 14) stageName = `Gameweek 14 • Round 2 (Round of 8)`;
      else if (gwNum === 19) stageName = `Gameweek 19 • Quarter-Finals (Top 4 Byes Enter)`;
      else if (gwNum === 24) stageName = `Gameweek 24 • Semi-Finals (Leg 1)`;
      else if (gwNum === 29) stageName = `Gameweek 29 • Semi-Finals (Leg 2)`;
      else if (gwNum === 34) stageName = `Gameweek 34 • Lingineni Cup Final 🏆`;

      html += `
        <div class="tournament-stage-header" style="color: #fbbf24; grid-column: 1 / -1; font-weight: 800; font-size: 1.05rem; margin-top: 16px; border-bottom: 1px solid var(--border-glass); padding-bottom: 4px;">
          <span>🏆 ${stageName}</span>
          <span style="font-size: 0.75rem; font-weight: 600; color: var(--text-muted); float: right;">${isGwCompleted ? '✓ Completed' : '• Scheduled'}</span>
        </div>
      `;

      if (gwFixtures.length === 0) {
        html += `
          <div class="matchup-card card-cup" style="grid-column: 1 / -1; text-align: center; padding: 16px;">
            <div style="font-size: 0.85rem; color: var(--text-muted);">Fixtures scheduled for ${stageName}</div>
          </div>
        `;
      } else {
        html += gwFixtures.map(m => renderMatchCard(m)).join("");
      }
    });

    container.innerHTML = html;
    return;
  }

  // Weekly View (all / league)
  const isCompleted = completedGws.includes(gameweek);
  let tourneyNote = "";
  if ([6, 11, 16, 21, 26, 31, 33, 36].includes(gameweek)) tourneyNote += " [⭐ Champions League Matchday]";
  if ([9, 14, 19, 24, 29, 34].includes(gameweek)) tourneyNote += " [🏆 Lingineni Cup Round]";

  if (gwTitle) {
    gwTitle.textContent = `Gameweek ${gameweek} ${isCompleted ? 'Official Results & Fixtures' : 'Scheduled Fixtures'}${tourneyNote}`;
  }

  let fixtures = LEAGUE_DATA.currentSeason.gameweekMatchups[gameweek] || [];
  if (filterType === 'league') {
    fixtures = fixtures.filter(f => f.competition === 'league');
  }

  if (fixtures.length === 0) {
    container.innerHTML = `
      <div class="card-panel" style="grid-column: 1 / -1; text-align: center; padding: 40px 20px;">
        <div style="font-size: 1.8rem; margin-bottom: 8px;">📅</div>
        <div style="font-family: var(--font-heading); font-size: 1.1rem; color: var(--text-main); font-weight: 700;">No fixtures found for Gameweek ${gameweek}</div>
        <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 4px;">Select another competition filter or change the gameweek selector above.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = fixtures.map(m => renderMatchCard(m)).join("");
}

function renderMatchCard(m) {
  const hasScores = (m.homeScore > 0 || m.awayScore > 0);
  const homeWin = hasScores && m.homeScore > m.awayScore;
  const awayWin = hasScores && m.awayScore > m.homeScore;

  let compBadge = `<span class="ticker-badge" style="background: rgba(255,255,255,0.05); color: var(--text-muted); border-color: var(--border-glass);">⚽ Premier League</span>`;
  let cardStyle = "";

  if (m.competition === 'champions_league' || m.isConcurrentCL) {
    compBadge = `<span class="ticker-badge" style="background: rgba(6, 182, 212, 0.12); color: var(--pl-cyan); border-color: rgba(6, 182, 212, 0.35);">⭐ Champions League ${m.clStage ? `• ${m.clStage}` : m.tournamentStage ? `• ${m.tournamentStage}` : ''}</span>`;
    cardStyle = "border-color: rgba(6, 182, 212, 0.35); background: linear-gradient(135deg, rgba(6, 182, 212, 0.05) 0%, rgba(15, 23, 42, 0.7) 100%);";
  } else if (m.competition === 'lingineni_cup') {
    compBadge = `<span class="ticker-badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border-color: rgba(245, 158, 11, 0.35);">🏆 Lingineni Cup • ${m.tournamentStage || 'Knockout Match'}</span>`;
    cardStyle = "border-color: rgba(245, 158, 11, 0.35); background: linear-gradient(135deg, rgba(245, 158, 11, 0.05) 0%, rgba(15, 23, 42, 0.7) 100%);";
  }

  return `
    <div class="matchup-card" style="${cardStyle}">
      <div class="matchup-header">
        <span>${compBadge}</span>
        <span style="font-size: 0.75rem; color: var(--text-muted);">${m.status || (hasScores ? 'Final' : 'Scheduled')}</span>
      </div>
      <div class="matchup-row" style="${homeWin ? 'font-weight: 700; color: var(--pl-green);' : ''}">
        <div>
          <div style="font-weight: 600; color: var(--text-main);">${m.home}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${m.homeTeam}</div>
        </div>
        <div class="matchup-score" style="color: ${homeWin ? 'var(--pl-green)' : 'inherit'};">
          ${hasScores ? m.homeScore.toFixed(2) : '—'}
        </div>
      </div>
      <div class="matchup-row" style="${awayWin ? 'font-weight: 700; color: var(--pl-green);' : ''}">
        <div>
          <div style="font-weight: 600; color: var(--text-main);">${m.away}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${m.awayTeam}</div>
        </div>
        <div class="matchup-score" style="color: ${awayWin ? 'var(--pl-green)' : 'inherit'};">
          ${hasScores ? m.awayScore.toFixed(2) : '—'}
        </div>
      </div>
    </div>
  `;
}

// 9. 14x14 Head-to-Head Matrix Grid
function renderH2HMatrix() {
  const container = document.getElementById("h2h-matrix-container");
  if (!container) return;

  const managers = LEAGUE_DATA.managers;
  let html = `<table class="h2h-table"><thead><tr><th>H2H</th>`;
  managers.forEach(m => {
    html += `<th>${m.shortName}</th>`;
  });
  html += `</tr></thead><tbody>`;

  managers.forEach(m1 => {
    html += `<tr><td style="font-weight:700; color: var(--text-main); text-align: left;">${m1.shortName}</td>`;
    managers.forEach(m2 => {
      if (m1.name === m2.name) {
        html += `<td style="background: rgba(255,255,255,0.03); color: var(--text-dim);">—</td>`;
      } else {
        const key = [m1.name, m2.name].sort().join(" vs ");
        const rec = LEAGUE_DATA.history.headToHeadMatrix[key] || { [m1.name]: 0, [m2.name]: 0, draws: 0 };
        const w1 = rec[m1.name] || 0;
        const w2 = rec[m2.name] || 0;
        const d = rec.draws || 0;

        let cellColor = "color: var(--text-muted);";
        if (w1 > w2) cellColor = "color: var(--pl-green); font-weight: 700;";
        else if (w1 < w2) cellColor = "color: #f87171;";

        html += `
          <td class="h2h-cell" style="${cellColor}" onclick="alert('All-Time Rivalry: ${m1.name} (${w1}W) - ${d}D - ${m2.name} (${w2}W)')">
            ${w1}-${w2}${d > 0 ? `-${d}` : ''}
          </td>
        `;
      }
    });
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;
}

// 10. Render Champions League Hub
function renderChampionsLeague() {
  const tbody = document.getElementById("cl-group-tbody");
  if (tbody) {
    const clData = LEAGUE_DATA.currentSeason.championsLeague;
    tbody.innerHTML = (clData.standings || []).map((row, idx) => `
      <tr>
        <td style="font-weight: 800; color: var(--pl-cyan);">${idx + 1}</td>
        <td>
          <div style="font-weight: 700; color: var(--text-main);">${row.manager}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${row.team}</div>
        </td>
        <td style="color: var(--pl-green); font-weight: 700;">${row.w}</td>
        <td>${row.d}</td>
        <td style="color: #f87171;">${row.l}</td>
        <td>${row.pf.toFixed(1)}</td>
        <td>${row.pa.toFixed(1)}</td>
        <td style="font-weight: 800; color: var(--text-highlight);">${row.pts}</td>
      </tr>
    `).join("");
  }

  const list = document.getElementById("cl-qualifiers-list");
  if (list) {
    const qualifiers = LEAGUE_DATA.currentSeason.championsLeague.qualifiers || [];
    list.innerHTML = qualifiers.map(q => `
      <div style="padding: 10px 14px; background: rgba(6, 182, 212, 0.06); border: 1px solid rgba(6, 182, 212, 0.25); border-radius: var(--radius-sm); display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div style="font-weight: 700; color: var(--text-main);">${q.manager}</div>
          <div style="font-size: 0.75rem; color: var(--pl-cyan);">${q.team}</div>
        </div>
        <span class="ticker-badge" style="background: rgba(6, 182, 212, 0.15); color: var(--pl-cyan); border-color: rgba(6, 182, 212, 0.4);">${q.reason}</span>
      </div>
    `).join("");
  }
}

// 11. Render Lingineni Cup Hub
function renderLingineniCup() {
  const container = document.getElementById("cup-rounds-tree");
  if (!container) return;

  const rounds = LEAGUE_DATA.currentSeason.lingineniCup.rounds || [];
  container.innerHTML = rounds.map(r => `
    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-glass); border-radius: var(--radius-md); padding: 16px;">
      <div style="font-family: var(--font-heading); font-size: 1rem; font-weight: 800; color: #fbbf24; margin-bottom: 8px;">${r.roundName} <span style="font-size: 0.75rem; color: var(--text-muted);">(Gameweek ${r.gameweek})</span></div>
      <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 12px;">${r.desc}</div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        ${(r.matches || []).map(m => `
          <div style="padding: 8px 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); font-size: 0.85rem; display: flex; justify-content: space-between;">
            <span>${m.homeTeam}</span>
            <span style="color: #fbbf24; font-weight: 700;">vs</span>
            <span>${m.awayTeam}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");
}

// 12. Render Manager Dossiers
function renderManagerDossiers() {
  const container = document.getElementById("managers-grid");
  if (!container) return;

  const managers = LEAGUE_DATA.managers || [];
  container.innerHTML = managers.map(m => `
    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-glass); border-radius: var(--radius-md); padding: 18px;">
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 14px;">
        <div style="width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, var(--pl-green), var(--pl-cyan)); color: #000; font-family: var(--font-heading); font-weight: 900; display: flex; align-items: center; justify-content: center; font-size: 1.1rem;">
          ${m.shortName}
        </div>
        <div>
          <div style="font-family: var(--font-heading); font-weight: 800; font-size: 1.1rem; color: var(--text-highlight);">${m.name}</div>
          <div style="font-size: 0.8rem; color: var(--pl-green); font-weight: 600;">${m.teamName}</div>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: var(--radius-sm); text-align: center; margin-bottom: 10px; font-size: 0.78rem;">
        <div><div style="color: var(--text-muted);">City</div><div style="font-weight:700;">${m.location || 'USA'}</div></div>
        <div><div style="color: var(--text-muted);">Purse</div><div style="font-weight:700; color: #fbbf24;">$${m.totalPrizeMoney || 0}</div></div>
        <div><div style="color: var(--text-muted);">Titles</div><div style="font-weight:700; color: var(--pl-green);">${m.championships || 0}</div></div>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">${m.bio || 'League competitor.'}</div>
    </div>
  `).join("");
}

// 13. Hall of Fame
function renderHallOfFame() {
  const container = document.getElementById("hall-of-fame-grid");
  if (!container) return;

  const champions = LEAGUE_DATA.history.pastChampions || [];
  container.innerHTML = champions.map(c => `
    <div style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(15, 23, 42, 0.8) 100%); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: var(--radius-md); padding: 20px; text-align: center;">
      <div style="font-size: 2rem; margin-bottom: 4px;">🏆</div>
      <div style="font-family: var(--font-heading); font-size: 1.2rem; font-weight: 800; color: #fbbf24;">${c.season} Champion</div>
      <div style="font-size: 1.1rem; font-weight: 700; color: var(--text-main); margin-top: 6px;">${c.manager}</div>
      <div style="font-size: 0.85rem; color: var(--pl-green); font-weight: 600;">${c.team}</div>
      <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">Record: ${c.record} • ${c.points} Pts</div>
    </div>
  `).join("");
}

// 14. Career Prize Money Leaderboard
function renderCareerPrizeMoney() {
  const tbody = document.getElementById("career-prizes-tbody");
  if (!tbody) return;

  let managers = [...LEAGUE_DATA.managers];
  const sort = APP_STATE.sorts['table-career-prizes'];
  if (sort) {
    sortDataArray(managers, sort.key, sort.dir, sort.type || 'num');
  }

  tbody.innerHTML = managers.map((m, idx) => `
    <tr>
      <td style="font-weight: 800; color: var(--pl-green);">${idx + 1}</td>
      <td style="font-weight: 700; color: var(--text-main);">${m.name}</td>
      <td>${m.teamName}</td>
      <td style="font-weight: 800; color: #fbbf24; font-size: 1.05rem;">$${m.totalPrizeMoney || 0}</td>
      <td>${m.careerPoints || 0}</td>
      <td>${m.ppg ? m.ppg.toFixed(1) : '—'}</td>
    </tr>
  `).join("");
}

// 15. Render Prize Pool Breakdown
function renderPrizePool() {
  const container = document.getElementById("prize-pool-cards");
  if (!container) return;

  const prizes = LEAGUE_DATA.metadata.prizeBreakdown || [
    { title: "League Champion (1st Place)", amount: 400, desc: "Premier League Winner trophy + $400 cash purse" },
    { title: "Weekly High Score Purse", amount: 380, desc: "$10 bonus cash prize per completed matchweek (38 weeks)" },
    { title: "Champions League Winner", amount: 200, desc: "Champions League Tournament victor" },
    { title: "Lingineni Cup Champion", amount: 170, desc: "Single Elimination Cup Winner" },
    { title: "League Runner-Up (2nd Place)", amount: 150, desc: "Premier League 2nd Place finisher" },
    { title: "League 3rd Place", amount: 100, desc: "Premier League 3rd Place finisher" }
  ];

  container.innerHTML = prizes.map(p => `
    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-glass); border-radius: var(--radius-md); padding: 18px;">
      <div style="font-family: var(--font-heading); font-size: 1.25rem; font-weight: 900; color: #fbbf24;">$${p.amount}</div>
      <div style="font-family: var(--font-heading); font-size: 1rem; font-weight: 700; color: var(--text-main); margin: 4px 0;">${p.title}</div>
      <div style="font-size: 0.82rem; color: var(--text-muted);">${p.desc}</div>
    </div>
  `).join("");
}

// 16. IHOP Calculator
function initIhopCalculator() {
  updateIhopCalculator(12);
}

function updateIhopCalculator(val) {
  const eaten = parseInt(val);
  const remaining = Math.max(0, 24 - eaten);
  const countEl = document.getElementById("pancake-count-val");
  const remEl = document.getElementById("ihop-hours-remaining");
  if (countEl) countEl.textContent = eaten;
  if (remEl) remEl.textContent = `${remaining} Hour${remaining === 1 ? '' : 's'}`;
}

// 17. Positional Scoring Matrix
function renderScoringMatrix(pos = "D") {
  const tbody = document.getElementById("scoring-matrix-tbody");
  if (!tbody) return;

  const matrix = LEAGUE_DATA.metadata.scoringMatrix || {};
  const posRules = matrix[pos] || [
    { action: "Goal Scored", code: "G", pts: 6.0, cat: "Attacking" },
    { action: "Goal Assist", code: "A", pts: 4.0, cat: "Attacking" },
    { action: "Clean Sheet", code: "CS", pts: 4.0, cat: "Defending" },
    { action: "Tackle Won", code: "T", pts: 1.0, cat: "Defending" },
    { action: "Interception", code: "I", pts: 0.5, cat: "Defending" }
  ];

  tbody.innerHTML = posRules.map(r => `
    <tr>
      <td style="font-weight: 700; color: var(--text-main);">${r.action}</td>
      <td><span class="ticker-badge">${r.code}</span></td>
      <td style="font-weight: 800; color: ${r.pts > 0 ? 'var(--pl-green)' : '#f87171'};">${r.pts > 0 ? `+${r.pts}` : r.pts}</td>
      <td style="color: var(--text-muted);">${r.cat}</td>
    </tr>
  `).join("");
}

// 18. Governance Bylaws Accordion
function renderBylawsAccordion() {
  const container = document.getElementById("bylaws-accordion");
  if (!container) return;

  const bylaws = LEAGUE_DATA.metadata.bylaws || [
    { title: "Article I: League Structure & Entry Fee", content: "14 Managers. $100 buy-in per manager collected prior to draft. $1,400 total purse." },
    { title: "Article II: Champions League Qualification", content: "Top 6 overall finishers in the Premier League table qualify for next season's Champions League tournament." },
    { title: "Article III: The 24-Hour IHOP Gauntlet Penalty", content: "The 14th place last place manager must spend 24 consecutive hours in an IHOP. Every pancake eaten reduces sentence by 1 hour." },
    { title: "Article IV: Roster & Waiver Rules", content: "FAAB waiver budget $100. Continuous waivers process Tuesday and Thursday nights." }
  ];

  container.innerHTML = bylaws.map(b => `
    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-glass); border-radius: var(--radius-md); padding: 16px;">
      <div style="font-family: var(--font-heading); font-size: 1rem; font-weight: 800; color: var(--pl-green); margin-bottom: 6px;">${b.title}</div>
      <div style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5;">${b.content}</div>
    </div>
  `).join("");
}

// 19. Gameweek Dropdown Population
function populateGameweekDropdown() {
  const select = document.getElementById("gw-selector-dropdown");
  if (!select) return;

  let options = "";
  const completedGws = LEAGUE_DATA.currentSeason.completedGameweeks || [1];
  for (let i = 1; i <= 38; i++) {
    const isCompleted = completedGws.includes(i);
    options += `<option value="${i}">Gameweek ${i} ${isCompleted ? '✓' : ''}</option>`;
  }
  select.innerHTML = options;
}

// 20. Table Sorting Helpers
function setupTableSortListeners() {
  document.querySelectorAll("table.fpl-table th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const table = th.closest("table");
      if (!table) return;

      const tableId = table.id;
      const sortKey = th.getAttribute("data-sort");
      const dataType = th.getAttribute("data-type") || "num";

      if (!APP_STATE.sorts[tableId]) {
        APP_STATE.sorts[tableId] = { key: sortKey, dir: 'asc', type: dataType };
      } else {
        const current = APP_STATE.sorts[tableId];
        if (current.key === sortKey) {
          current.dir = (current.dir === 'asc') ? 'desc' : 'asc';
        } else {
          current.key = sortKey;
          current.dir = 'asc';
          current.type = dataType;
        }
      }

      // Re-render
      if (tableId === 'table-official-standings') renderOfficialStandings();
      else if (tableId === 'table-optimal-standings') renderOptimalStandings();
      else if (tableId === 'table-median-standings') renderMedianStandings();
      else if (tableId === 'table-lineup-efficiency') renderManagerEfficiency();
      else if (tableId === 'table-career-prizes') renderCareerPrizeMoney();
    });
  });
}

function sortDataArray(arr, key, dir, type = 'num') {
  arr.sort((a, b) => {
    let v1 = a[key];
    let v2 = b[key];
    if (type === 'num') {
      v1 = parseFloat(v1) || 0;
      v2 = parseFloat(v2) || 0;
    } else {
      v1 = String(v1).toLowerCase();
      v2 = String(v2).toLowerCase();
    }

    if (v1 < v2) return dir === 'asc' ? -1 : 1;
    if (v1 > v2) return dir === 'asc' ? 1 : -1;
    return 0;
  });
}
