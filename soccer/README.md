# Soccer Analytics & Fantasy FPL Suite

An end-to-end Python analytics toolkit and interactive draft ranking web application for Fantasy Premier League (FPL) and Fantrax.

---

## 📦 Projects Overview

### 1. [`fantrax_wrapper/`](./fantrax_wrapper)
A clean, modular, fully typed Python SDK for Fantrax Fantasy Premier League data.
- **Features**: Cookie & Selenium authentication, JSON-RPC protocol client, customizable scoring engine, manager efficiency benchmarks, optimal lineup solver, median standings, per-90 stat normalization, and waiver target recommendations.
- **Documentation**: [fantrax_wrapper README](./fantrax_wrapper/README.md)

### 2. [`pitchrank/`](./pitchrank)
An interactive web application for draft day tier list generation and player ranking.
- **Features**: Pairwise head-to-head duels using binary insertion search ($O(N \log N)$), responsive desktop UI with keyboard shortcuts, iPhone single-page (`100dvh`) touch UI with swipe gestures, multi-sheet Excel export, and native dependency-free CSV export.
- **Documentation**: [pitchrank README](./pitchrank/README.md)

### 3. Additional Modules
- **`config/`**: Shared configuration and environment settings (`soccer/config/.env`).
- **`examples/`**: Ready-to-run Python scripts demonstrating API wrapper usage.
- **`fpts_model/`**: Per-stat random forest model. Each gameweek gets its own model, trained on all earlier games, and a prediction for every player (`pip install -r soccer/fpts_model/requirements.txt`, then `python3 -m fpts_model.train` from `soccer/`). The League Hub and Commish Bot read the saved predictions. See the [fpts_model README](./fpts_model/README.md) for how each feature is built. Models train on this season plus past seasons in `fpts_model/game_logs/`, with older games counting for less. Model files stay local, ignored by git; `--rebuild-models` recreates any that are missing.
- **`research/`**: Exploratory data science notebooks and statistical modeling scripts.
- **`tests/`**: Pytest test suite for backend analytics and API models.

---

## 🚀 Quick Execution Commands

- **Run PitchRank FPL Web App**:
  ```bash
  python3 soccer/pitchrank/app.py
  ```
- **Run Fantrax Wrapper Examples**:
  ```bash
  python3 soccer/examples/league_summary.py
  ```
- **Run Automated Test Suite**:
  ```bash
  pytest soccer/tests/
  ```
