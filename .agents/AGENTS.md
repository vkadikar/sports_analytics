# Workspace Context & Agent Guidelines — Sports Analytics Suite

Welcome to the **Sports Analytics Suite** repository. This document provides a complete architecture overview, design conventions, and operational guidelines for future AI coding agents working in this workspace.

---

## 📁 Repository Structure

```
/Users/varunkadikar/Desktop/sports_analytics/
├── .agents/
│   └── AGENTS.md                  # <-- This file: Agent guidelines & architecture
├── fantraxloggedin.cookie          # Serialized Fantrax session cookie
├── requirements.txt                # Global Python dependencies
└── soccer/
    ├── config/                    # Configuration & .env settings
    │   └── .env                   # Environment variables (FANTRAX_LEAGUE_ID, etc.)
    ├── fantrax_wrapper/           # Python Fantrax API Wrapper SDK
    │   ├── __init__.py            # Package exports
    │   ├── client.py              # Main user-facing FantraxClient class
    │   ├── session.py             # Cookie & Selenium auth session manager
    │   ├── rpc.py                 # RPC JSON-RPC network client
    │   ├── scoring.py             # Customizable Fantasy Scoring Engine
    │   ├── models/                # Dataclasses & Pydantic models
    │   ├── analytics/             # Manager efficiency, waiver evaluation, per-90 stats
    │   └── utils.py               # Helper utilities (env loader, string parsers)
    ├── pitchrank/                 # PitchRank FPL Web Application
    │   ├── app.py                 # Lightweight Python HTTP server
    │   ├── generate_player_data.py# Script to pre-compute ADP & projection datasets
    │   ├── index.html             # Main single-page web interface
    │   ├── style.css              # Custom CSS with responsive mobile 100dvh design
    │   ├── app.js                 # Binary insertion search engine & state manager
    │   ├── players_data.json      # Positional dataset (Forwards, Mids, Defs, GKs)
    │   └── render.yaml            # Render deployment configuration
    ├── examples/                  # Python scripts & Jupyter notebooks demonstrating wrapper usage
    ├── research/                  # Data science & statistical analysis scripts
    └── tests/                     # Pytest suite for fantrax_wrapper
```

---

## 🚀 Key Projects

### 1. Fantrax API Wrapper (`soccer/fantrax_wrapper`)
A modular, fully-typed, object-oriented Python library designed to query and analyze Fantasy Premier League data from Fantrax.

- **Primary Client (`FantraxClient`)**: Instantiated with `league_id` (or loaded automatically from `FANTRAX_LEAGUE_ID` in `soccer/config/.env`).
- **Session Manager (`FantraxSessionManager`)**: Handles cookie authentication (`fantraxloggedin.cookie`) with fallback to headless browser login (Selenium/WebDriverManager).
- **RPC Layer (`FantraxRPCClient`)**: Executes POST requests against Fantrax's JSON-RPC endpoint (`/fx/api/req`).
- **Scoring Engine (`FantasyScoringEngine`)**: Maps raw box score stats to customizable fantasy scoring rules.
- **Analytics Engine (`analytics/`)**:
  - `compute_optimal_lineup_score`: Calculates maximum possible lineup points per Gameweek.
  - `calculate_manager_efficiency`: Benchmarks actual points vs optimal points.
  - `calculate_median_standings`: Simulates standings with median bonus points.
  - `evaluate_waiver_candidates`: Ranks free agents based on form, per-90 metrics, and opponent strength.
  - `normalize_per_90_stats`: Standardizes counting stats to 90-minute rates.

### 2. PitchRank FPL (`soccer/pitchrank`)
An interactive, responsive web application for Fantasy Premier League draft preparation.

- **Algorithm**: Replaces tedious drag-and-drop ranking with **binary insertion sort duels** ($O(N \log N)$ total comparisons, $O(\log N)$ per player).
- **Responsive Layout**:
  - **Desktop**: Full workspace with side-by-side cards, hotkeys (`←`, `→`, `S`, `Z`), and detailed stats.
  - **Mobile / iPhone**: Single-page (`100dvh`, zero-scroll) viewport with vertically stacked hero stat cards, touch swipe gestures (Swipe Left/Right to pick, Swipe Down to skip), pinned 1-thumb action buttons, and bottom tab navigation (`⚔️ Duels` / `📋 Board`).
- **Data Export**: Supports multi-sheet Excel (`.xlsx`) via SheetJS and native dependency-free CSV (`.csv`) export.

---

## 🛠️ Command Cheat Sheet for Agents

### Running PitchRank Locally
```bash
python3 soccer/pitchrank/app.py
```
Open **`http://localhost:8000`** (or port specified in terminal).

### Running Tests
```bash
pytest soccer/tests/
```

### Running Fantrax Analytics Scripts
```bash
python3 soccer/examples/league_summary.py
```

---

## ⚠️ Important Rules for Agents

1. **Dependency Management**: Use existing dependencies in `requirements.txt`. Do not install global packages without isolated environments.
2. **UI & Styling**: Preserve the dark glassmorphic design system (`#080c14` background, `#10b981` FPL green accent). Ensure mobile UI maintains `height: 100dvh` without vertical scroll leakage.
3. **Data Quality**: Avoid hardcoding static offsets or dummy placeholders. Verify dataset properties in `players_data.json` before modifying frontend render logic.
