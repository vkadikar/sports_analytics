document.addEventListener("DOMContentLoaded", () => {
  // State variables
  let rawData = {};
  let currentPosition = "F"; // "F", "M", "D", "G"
  let currentView = "matchup"; // "matchup" or "board"

  // Per-position state structure
  // state[pos] = { rankedList: [], unrankedQueue: [], skippedList: [], currentInsertion: { item, low, high }, history: [] }
  let state = {};

  // DOM Elements
  const positionTabs = document.getElementById("positionTabs");
  const matchupModeBtn = document.getElementById("matchupModeBtn");
  const boardModeBtn = document.getElementById("boardModeBtn");
  const matchupView = document.getElementById("matchupView");
  const boardView = document.getElementById("boardView");

  const progressText = document.getElementById("progressText");
  const progressBarFill = document.getElementById("progressBarFill");
  const rankedCountBadge = document.getElementById("rankedCountBadge");

  const undoBtn = document.getElementById("undoBtn");
  const resetPosBtn = document.getElementById("resetPosBtn");
  const exportExcelBtn = document.getElementById("exportExcelBtn");
  const continueRankingBtn = document.getElementById("continueRankingBtn");

  // Player Cards & Skip
  const leftPlayerCard = document.getElementById("leftPlayerCard");
  const rightPlayerCard = document.getElementById("rightPlayerCard");
  const chooseLeftBtn = document.getElementById("chooseLeftBtn");
  const chooseRightBtn = document.getElementById("chooseRightBtn");
  const skipBtn = document.getElementById("skipBtn");

  const rankedListContainer = document.getElementById("rankedListContainer");
  const skippedListContainer = document.getElementById("skippedListContainer");
  const skippedSection = document.getElementById("skippedSection");
  const skippedCount = document.getElementById("skippedCount");
  const boardPosName = document.getElementById("boardPosName");

  // Initialize
  init();

  async function init() {
    try {
      const response = await fetch("players_data.json");
      rawData = await response.json();
    } catch (err) {
      console.error("Error loading players_data.json:", err);
      alert("Failed to load player data. Please ensure the app server is running.");
      return;
    }

    // Update count pills dynamically
    document.getElementById("cntF").textContent = (rawData["F"] || []).length;
    document.getElementById("cntM").textContent = (rawData["M"] || []).length;
    document.getElementById("cntD").textContent = (rawData["D"] || []).length;
    document.getElementById("cntG").textContent = (rawData["G"] || []).length;

    loadStateFromStorage();
    setupEventListeners();
    renderCurrentPosition();
  }

  function initStateForPosition(pos) {
    if (!state[pos]) {
      const players = rawData[pos] || [];
      state[pos] = {
        rankedList: [], // Array of players currently ranked
        unrankedQueue: [...players], // Players left to insert
        skippedList: [], // Players skipped by user
        currentInsertion: null, // { item, low, high }
        history: [], // Stack for Undo
      };
      advanceInsertion(pos);
    }
  }

  function advanceInsertion(pos) {
    const posState = state[pos];
    if (posState.currentInsertion) return; // Already in progress

    if (posState.unrankedQueue.length === 0) {
      posState.currentInsertion = null;
      return;
    }

    // Pick next unranked player
    const nextItem = posState.unrankedQueue.shift();

    if (posState.rankedList.length === 0) {
      // First item is automatically placed at index 0
      posState.rankedList.push(nextItem);
      advanceInsertion(pos);
    } else {
      // Initialize binary insertion search
      posState.currentInsertion = {
        item: nextItem,
        low: 0,
        high: posState.rankedList.length - 1,
      };
    }
  }

  function renderCurrentPosition() {
    initStateForPosition(currentPosition);

    // Update Tab active state
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      if (btn.dataset.pos === currentPosition) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    // Update Progress
    const posState = state[currentPosition];
    const totalPlayers = (rawData[currentPosition] || []).length;
    const rankedCount = posState.rankedList.length;
    const skippedCnt = (posState.skippedList || []).length;
    const processedCount = rankedCount + skippedCnt;
    const percent = totalPlayers > 0 ? Math.round((processedCount / totalPlayers) * 100) : 0;

    progressText.textContent = `${percent}% (${rankedCount}/${totalPlayers} Ranked)`;
    progressBarFill.style.width = `${percent}%`;
    rankedCountBadge.textContent = `${rankedCount}/${totalPlayers}`;

    // Enable/Disable Undo Button
    undoBtn.disabled = posState.history.length === 0;

    // Render active view
    if (currentView === "matchup") {
      matchupView.classList.add("active");
      boardView.classList.remove("active");
      matchupModeBtn.classList.add("active");
      boardModeBtn.classList.remove("active");
      renderMatchup();
    } else {
      boardView.classList.add("active");
      matchupView.classList.remove("active");
      boardModeBtn.classList.add("active");
      matchupModeBtn.classList.remove("active");
      renderBoard();
    }

    saveStateToStorage();
  }

  function renderMatchup() {
    const posState = state[currentPosition];
    const currentIns = posState.currentInsertion;

    if (!currentIns) {
      // Ranking for this position is complete!
      const totalPlayers = (rawData[currentPosition] || []).length;
      matchupView.innerHTML = `
        <div class="duel-instruction" style="padding: 40px; text-align: center;">
          <div style="font-size: 48px; margin-bottom: 12px;">🎉</div>
          <h2 style="font-size: 26px; color: var(--accent-fpl);">Position Ranking Complete for ${getPositionFullName(currentPosition)}!</h2>
          <p style="color: var(--text-muted); margin-top: 8px; font-size: 15px;">
            You have processed all ${totalPlayers} players (${posState.rankedList.length} ranked, ${posState.skippedList.length} skipped).
          </p>
          <button id="viewBoardBtn" class="action-btn primary-btn" style="margin: 24px auto 0; font-size: 15px; padding: 12px 24px;">
            📋 View Ranked Leaderboard
          </button>
        </div>
      `;
      document.getElementById("viewBoardBtn")?.addEventListener("click", () => {
        currentView = "board";
        renderCurrentPosition();
      });
      return;
    }

    const mid = Math.floor((currentIns.low + currentIns.high) / 2);
    const leftItem = currentIns.item; // Player being inserted
    const rightItem = posState.rankedList[mid]; // Player to compare against

    fillPlayerCard("left", leftItem);
    fillPlayerCard("right", rightItem);
  }

  function fillPlayerCard(side, player) {
    document.getElementById(`${side}Pos`).textContent = player.position;
    document.getElementById(`${side}Pos`).className = `pos-tag pos-${player.position.toLowerCase()}`;
    document.getElementById(`${side}Team`).textContent = player.team;
    document.getElementById(`${side}Name`).textContent = player.name;
    document.getElementById(`${side}Adp`).textContent = player.adp;
    document.getElementById(`${side}Proj`).textContent = player.projected_pts;
    document.getElementById(`${side}Pts2025`).textContent = player.pts_2025;
    document.getElementById(`${side}Pts2024`).textContent = player.pts_2024;
  }

  function makeChoice(winnerSide) {
    const posState = state[currentPosition];
    const currentIns = posState.currentInsertion;
    if (!currentIns) return;

    // Save snapshot for Undo
    saveHistorySnapshot(posState);

    const mid = Math.floor((currentIns.low + currentIns.high) / 2);

    if (winnerSide === "left") {
      // Left player (being inserted) is BETTER than mid player -> search upper half (smaller index)
      currentIns.high = mid - 1;
    } else {
      // Right player (mid player) is BETTER than left player -> search lower half (larger index)
      currentIns.low = mid + 1;
    }

    if (currentIns.low > currentIns.high) {
      // Found exact insertion position at index `currentIns.low`
      posState.rankedList.splice(currentIns.low, 0, currentIns.item);
      posState.currentInsertion = null;
      advanceInsertion(currentPosition);
    }

    renderCurrentPosition();
  }

  function skipPlayer() {
    const posState = state[currentPosition];
    const currentIns = posState.currentInsertion;
    if (!currentIns) return;

    // Save snapshot for Undo
    saveHistorySnapshot(posState);

    // Add player to skipped list
    posState.skippedList.push(currentIns.item);
    posState.currentInsertion = null;
    advanceInsertion(currentPosition);

    renderCurrentPosition();
  }

  function saveHistorySnapshot(posState) {
    posState.history.push(JSON.parse(JSON.stringify({
      rankedList: posState.rankedList,
      unrankedQueue: posState.unrankedQueue,
      skippedList: posState.skippedList,
      currentInsertion: posState.currentInsertion,
    })));
  }

  function undoChoice() {
    const posState = state[currentPosition];
    if (!posState || posState.history.length === 0) return;

    const previousSnapshot = posState.history.pop();
    posState.rankedList = previousSnapshot.rankedList;
    posState.unrankedQueue = previousSnapshot.unrankedQueue;
    posState.skippedList = previousSnapshot.skippedList;
    posState.currentInsertion = previousSnapshot.currentInsertion;

    renderCurrentPosition();
  }

  function resetPosition() {
    if (confirm(`Are you sure you want to reset rankings for ${getPositionFullName(currentPosition)}?`)) {
      delete state[currentPosition];
      renderCurrentPosition();
    }
  }

  function renderBoard() {
    const posState = state[currentPosition];
    boardPosName.textContent = getPositionFullName(currentPosition);

    if (posState.rankedList.length === 0 && posState.skippedList.length === 0) {
      rankedListContainer.innerHTML = `
        <div style="padding: 40px; text-align: center; color: var(--text-muted);">
          <p style="font-size: 15px;">No players processed yet for ${getPositionFullName(currentPosition)}.</p>
          <button id="startMatchupBtn" class="action-btn primary-btn" style="margin: 16px auto 0;">
            ⚡ Start Matchup Duels
          </button>
        </div>
      `;
      document.getElementById("startMatchupBtn")?.addEventListener("click", () => {
        currentView = "matchup";
        renderCurrentPosition();
      });
      skippedSection.style.display = "none";
      return;
    }

    let html = "";
    posState.rankedList.forEach((player, idx) => {
      const rank = idx + 1;
      html += `
        <div class="ranked-item" data-index="${idx}">
          <div class="item-left">
            <span class="item-rank">#${rank}</span>
            <span class="pos-badge pos-${player.position.toLowerCase()}">${player.position}</span>
            <div class="item-info">
              <span class="item-name">${player.name}</span>
              <span class="item-meta">${player.team} | ADP: <strong>${player.adp}</strong></span>
            </div>
          </div>
          <div class="item-stats">
            <div class="item-stat-pill">
              <span class="item-stat-lbl">2026 Proj</span>
              <span class="item-stat-val" style="color: var(--accent-fpl);">${player.projected_pts}</span>
            </div>
            <div class="item-stat-pill">
              <span class="item-stat-lbl">2025 Actual</span>
              <span class="item-stat-val">${player.pts_2025}</span>
            </div>
            <div class="item-stat-pill">
              <span class="item-stat-lbl">2024 Actual</span>
              <span class="item-stat-val">${player.pts_2024}</span>
            </div>
            <div class="reorder-btns">
              <button class="reorder-btn move-up-btn" data-idx="${idx}" ${idx === 0 ? "disabled" : ""}>▲</button>
              <button class="reorder-btn move-down-btn" data-idx="${idx}" ${idx === posState.rankedList.length - 1 ? "disabled" : ""}>▼</button>
            </div>
          </div>
        </div>
      `;
    });

    rankedListContainer.innerHTML = html;

    // Attach reorder listeners
    document.querySelectorAll(".move-up-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.target.dataset.idx);
        if (idx > 0) {
          const item = posState.rankedList.splice(idx, 1)[0];
          posState.rankedList.splice(idx - 1, 0, item);
          renderCurrentPosition();
        }
      });
    });

    document.querySelectorAll(".move-down-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.target.dataset.idx);
        if (idx < posState.rankedList.length - 1) {
          const item = posState.rankedList.splice(idx, 1)[0];
          posState.rankedList.splice(idx + 1, 0, item);
          renderCurrentPosition();
        }
      });
    });

    // Render Skipped Players List
    if (posState.skippedList && posState.skippedList.length > 0) {
      skippedSection.style.display = "block";
      skippedCount.textContent = posState.skippedList.length;

      let skipHtml = "";
      posState.skippedList.forEach((player, sIdx) => {
        skipHtml += `
          <div class="ranked-item skipped-item">
            <div class="item-left">
              <span class="pos-badge pos-${player.position.toLowerCase()}">${player.position}</span>
              <div class="item-info">
                <span class="item-name">${player.name}</span>
                <span class="item-meta">${player.team} | ADP: <strong>${player.adp}</strong></span>
              </div>
            </div>
            <div class="item-stats">
              <button class="ctrl-btn rerank-btn" data-sidx="${sIdx}">⚡ Rank Player</button>
            </div>
          </div>
        `;
      });

      skippedListContainer.innerHTML = skipHtml;

      document.querySelectorAll(".rerank-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const sIdx = parseInt(e.target.dataset.sidx);
          const item = posState.skippedList.splice(sIdx, 1)[0];
          posState.unrankedQueue.unshift(item); // Put at front of unranked queue
          renderCurrentPosition();
        });
      });
    } else {
      skippedSection.style.display = "none";
    }
  }

  // Multi-Sheet Excel Workbook Export (.xlsx)
  function exportExcel() {
    if (typeof XLSX === "undefined") {
      alert("SheetJS library is loading. Please try exporting again in a moment.");
      return;
    }

    const wb = XLSX.utils.book_new();

    const positionConfig = [
      { code: "F", name: "Forwards" },
      { code: "M", name: "Midfielders" },
      { code: "D", name: "Defenders" },
      { code: "G", name: "Goalkeepers" },
    ];

    positionConfig.forEach(({ code, name }) => {
      const rows = [];
      const posState = state[code];

      // 1. Ranked Players
      if (posState && posState.rankedList) {
        posState.rankedList.forEach((player, idx) => {
          rows.push({
            "Position Rank": idx + 1,
            "Status": "RANKED",
            "Player Name": player.name,
            "Team": player.team,
            "Position": player.position,
            "ADP": player.adp,
            "2026 Projected Pts": player.projected_pts,
            "2025 Actual Pts": player.pts_2025,
            "2024 Actual Pts": player.pts_2024,
          });
        });
      }

      // 2. Skipped Players
      if (posState && posState.skippedList) {
        posState.skippedList.forEach((player) => {
          rows.push({
            "Position Rank": "UNRANKED",
            "Status": "SKIPPED",
            "Player Name": player.name,
            "Team": player.team,
            "Position": player.position,
            "ADP": player.adp,
            "2026 Projected Pts": player.projected_pts,
            "2025 Actual Pts": player.pts_2025,
            "2024 Actual Pts": player.pts_2024,
          });
        });
      }

      // Fallback if no players processed for this position yet
      if (rows.length === 0) {
        rows.push({
          "Position Rank": "-",
          "Status": "NO_DATA",
          "Player Name": "No players ranked yet for this position.",
          "Team": "-",
          "Position": code,
          "ADP": "-",
          "2026 Projected Pts": "-",
          "2025 Actual Pts": "-",
          "2024 Actual Pts": "-",
        });
      }

      // Create sheet and append to workbook
      const ws = XLSX.utils.json_to_sheet(rows);

      // Set column widths for clean readability
      ws['!cols'] = [
        { wch: 14 }, // Position Rank
        { wch: 10 }, // Status
        { wch: 24 }, // Player Name
        { wch: 18 }, // Team
        { wch: 10 }, // Position
        { wch: 10 }, // ADP
        { wch: 18 }, // 2026 Projected Pts
        { wch: 16 }, // 2025 Actual Pts
        { wch: 16 }, // 2024 Actual Pts
      ];

      XLSX.utils.book_append_sheet(wb, ws, name);
    });

    // Write multi-sheet Excel file (.xlsx)
    XLSX.writeFile(wb, `pitchrank_fpl_draft_rankings.xlsx`);
  }

  function setupEventListeners() {
    // Position tabs
    positionTabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".tab-btn");
      if (btn) {
        currentPosition = btn.dataset.pos;
        renderCurrentPosition();
      }
    });

    // View toggles
    matchupModeBtn.addEventListener("click", () => {
      currentView = "matchup";
      renderCurrentPosition();
    });

    boardModeBtn.addEventListener("click", () => {
      currentView = "board";
      renderCurrentPosition();
    });

    continueRankingBtn.addEventListener("click", () => {
      currentView = "matchup";
      renderCurrentPosition();
    });

    // Choices & Skip
    chooseLeftBtn.addEventListener("click", () => makeChoice("left"));
    chooseRightBtn.addEventListener("click", () => makeChoice("right"));
    leftPlayerCard.addEventListener("click", () => makeChoice("left"));
    rightPlayerCard.addEventListener("click", () => makeChoice("right"));
    skipBtn.addEventListener("click", skipPlayer);

    // Mobile Action Buttons
    document.getElementById("mobileChooseLeftBtn")?.addEventListener("click", () => makeChoice("left"));
    document.getElementById("mobileChooseRightBtn")?.addEventListener("click", () => makeChoice("right"));
    document.getElementById("mobileSkipBtn")?.addEventListener("click", skipPlayer);

    // Keyboard Hotkeys
    document.addEventListener("keydown", (e) => {
      if (currentView === "matchup") {
        if (e.key === "ArrowLeft") makeChoice("left");
        if (e.key === "ArrowRight") makeChoice("right");
        if (e.key === "ArrowDown" || e.key === "s" || e.key === "S") skipPlayer();
        if (e.key === "z" && (e.ctrlKey || e.metaKey)) undoChoice();
      }
    });

    // Controls
    undoBtn.addEventListener("click", undoChoice);
    resetPosBtn.addEventListener("click", resetPosition);
    exportExcelBtn.addEventListener("click", exportExcel);

    // Touch Swipe Gestures for Mobile & iPhone
    setupTouchGestures();
  }

  function setupTouchGestures() {
    const duelStage = document.getElementById("duelStage");
    if (!duelStage) return;

    const overlayLeft = document.getElementById("swipeOverlayLeft");
    const overlayRight = document.getElementById("swipeOverlayRight");
    const overlaySkip = document.getElementById("swipeOverlaySkip");

    let startX = 0;
    let startY = 0;
    let currentX = 0;
    let currentY = 0;
    let isDragging = false;

    duelStage.addEventListener("touchstart", (e) => {
      if (currentView !== "matchup") return;
      if (e.target.closest("button") || e.target.closest("a")) return;
      if (e.touches.length !== 1) return;

      const touch = e.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      currentX = startX;
      currentY = startY;
      isDragging = true;
      duelStage.classList.add("swiping");
    }, { passive: true });

    duelStage.addEventListener("touchmove", (e) => {
      if (!isDragging) return;
      const touch = e.touches[0];
      currentX = touch.clientX;
      currentY = touch.clientY;

      const deltaX = currentX - startX;
      const deltaY = currentY - startY;

      // Card tilt & drag translation
      const rotation = deltaX * 0.06;
      duelStage.style.transform = `translate3d(${deltaX}px, ${deltaY}px, 0) rotate(${rotation}deg)`;

      // Visual Overlay Badges
      overlayLeft?.classList.remove("active");
      overlayRight?.classList.remove("active");
      overlaySkip?.classList.remove("active");

      if (deltaX < -50 && Math.abs(deltaY) < Math.abs(deltaX)) {
        overlayLeft?.classList.add("active");
      } else if (deltaX > 50 && Math.abs(deltaY) < Math.abs(deltaX)) {
        overlayRight?.classList.add("active");
      } else if (deltaY > 50 && Math.abs(deltaX) < 45) {
        overlaySkip?.classList.add("active");
      }
    }, { passive: true });

    const resetStageTransform = () => {
      duelStage.classList.remove("swiping");
      duelStage.style.transform = "";
      overlayLeft?.classList.remove("active");
      overlayRight?.classList.remove("active");
      overlaySkip?.classList.remove("active");
    };

    const handleTouchEnd = () => {
      if (!isDragging) return;
      isDragging = false;

      const deltaX = currentX - startX;
      const deltaY = currentY - startY;

      if (deltaX < -65 && Math.abs(deltaY) < Math.abs(deltaX)) {
        resetStageTransform();
        makeChoice("left");
      } else if (deltaX > 65 && Math.abs(deltaY) < Math.abs(deltaX)) {
        resetStageTransform();
        makeChoice("right");
      } else if (deltaY > 65 && Math.abs(deltaX) < 50) {
        resetStageTransform();
        skipPlayer();
      } else {
        duelStage.style.transition = "transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275)";
        resetStageTransform();
        setTimeout(() => {
          duelStage.style.transition = "";
        }, 250);
      }
    };

    duelStage.addEventListener("touchend", handleTouchEnd);
    duelStage.addEventListener("touchcancel", handleTouchEnd);
  }

  function getPositionFullName(pos) {
    const map = { F: "Forwards", M: "Midfielders", D: "Defenders", G: "Goalkeepers" };
    return map[pos] || pos;
  }

  function saveStateToStorage() {
    try {
      localStorage.setItem("pitchrank_fpl_state", JSON.stringify(state));
    } catch (e) {}
  }

  function loadStateFromStorage() {
    try {
      const stored = localStorage.getItem("pitchrank_fpl_state");
      if (stored) state = JSON.parse(stored);
    } catch (e) {}
  }
});
