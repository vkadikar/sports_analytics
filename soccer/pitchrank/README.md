# PitchRank FPL — Premier League Draft Tier List Generator & Head-to-Head Ranker

**PitchRank FPL** is an interactive web application designed to help Fantasy Premier League (FPL) draft managers quickly generate personalized draft rankings.

Instead of manually sorting hundreds of players on a clunky drag-and-drop board, PitchRank uses **pairwise head-to-head duels** powered by a **binary insertion search algorithm** to build precise positional rankings in minimal comparisons.

---

## 🌟 Features & Highlights

### ⚡ Binary Insertion Search Algorithm
- Reduces full list ordering from $O(N^2)$ manual comparison fatigue to **$O(N \log N)$ total decisions** ($O(\log N)$ comparisons per player).
- Supports 4 positional pools:
  - ⚽ **Forwards (F)**: ~142 players
  - 🎯 **Midfielders (M)**: ~247 players
  - 🛡️ **Defenders (D)**: ~228 players
  - 🧤 **Goalkeepers (G)**: ~81 players

### 📥 Excel & CSV File Import & Resumption
- **Upload Previously Saved File**: Upload any PitchRank Excel workbook (`.xlsx`, `.xls`) or CSV file (`.csv`).
- **Seamless State Restoration**: Restores exact positional rankings (`RANKED` players) and skipped players (`SKIPPED`).
- **Resumes Where You Left Off**: Rebuilds the remaining `unrankedQueue` and automatically restarts binary insertion search duels from the exact player where you left off.

### 📱 Responsive Desktop & Single-Page Mobile UI (`100dvh`)
- **Desktop Mode**:
  - Side-by-side player card comparison with detailed projections and actual points.
  - Keyboard hotkeys: `←` Select Left, `→` Select Right, `S` or `↓` Skip Player, `Ctrl+Z` Undo.
- **Mobile / iPhone Mode (`100dvh`, Zero Vertical Scroll)**:
  - **Single Page Viewport**: Entire matchup view fits inside `100dvh` without page scrolling.
  - **Centered Player Typography**: Player name prominently centered with gold `ADP` badge.
  - **3-Column Stats Footer Row**: Shows `2026 PROJ` (highlighted), `2025 ACTUAL`, and `2024 ACTUAL` points side-by-side.
  - **Touch Swipe Gestures**: Swipe Left to select left player, Swipe Right for right player, Swipe Down to skip.
  - **Pinned Controls & Navigation**: Pinned 1-thumb quick action buttons (`👈 Left`, `⏭️ Skip`, `Right 👉`) and bottom tab bar (`⚔️ Duels` / `📋 Board`).

### 📊 Comprehensive Data Export
- **Native Dependency-Free CSV Export (`.csv`)**: Export draft rankings across all position groups with zero external library requirements. Works 100% offline.
- **Multi-Sheet Excel Export (`.xlsx`)**: Generates an Excel workbook with dedicated tabs for Forwards, Midfielders, Defenders, and Goalkeepers.

---

## 📁 File Structure

```
pitchrank/
├── app.py                 # Lightweight Python HTTP web server
├── app.js                 # Binary insertion search, state management, import/export parsers & gestures
├── index.html             # HTML layout with responsive header, import/export buttons, matchup view, board view, and bottom nav
├── style.css              # Custom CSS design system with desktop & mobile 100dvh responsive rules
├── generate_player_data.py# Data ETL script parsing underlying FPL player stats
├── players_data.json      # Pre-computed positional player datasets
├── render.yaml            # Render web service deployment configuration
└── Procfile               # Gunicorn / Python process runner
```

---

## 🚀 Running Locally

Launch the app server using Python:

```bash
python3 soccer/pitchrank/app.py
```

Then open **`http://localhost:8000`** in your browser.

---

## ☁️ Deployment

The project includes `render.yaml` and `Procfile` ready for one-click deployment on Render:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python app.py` (or `gunicorn app:app`)
