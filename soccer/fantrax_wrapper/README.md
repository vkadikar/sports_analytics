# Fantrax API Wrapper for Fantasy Premier League

A clean, modular, fully typed Python SDK and wrapper library for fetching, parsing, and analyzing Fantrax Fantasy Premier League (FPL) league data.

---

## 🌟 Architecture & Features

```
fantrax_wrapper/
├── __init__.py           # Package exports & version
├── client.py             # Main user-facing FantraxClient class
├── session.py            # Session management & cookie/Selenium auth
├── rpc.py                # Low-level JSON-RPC client (/fx/api/req)
├── scoring.py            # Customizable Fantasy Scoring Engine
├── utils.py              # String parsing & env loading helpers
├── models/               # Dataclass & Pydantic data schemas
│   ├── league.py         # LeagueInfo, StandingRow, WeeklyMatchup
│   ├── team.py           # Team, TeamRoster, RosterRow
│   ├── player.py         # PlayerSummary, PlayerProfile, GameLogEntry
│   └── analytics.py      # ManagerEfficiency, OptimalLineup, WaiverCandidate
└── analytics/            # High-level analytical algorithms
    ├── lineup.py         # Optimal lineup solver
    ├── efficiency.py     # Manager decision efficiency benchmarks
    ├── standings.py      # Median standings calculations
    ├── waivers.py         # Waiver & free agent candidate scoring
    └── stats.py          # Per-90 normalization & opponent averages
```

### Key Capabilities

1. **Authentication Management (`FantraxSessionManager`)**:
   - Automated cookie loading (`fantraxloggedin.cookie`).
   - Headless browser login via Selenium / WebDriverManager for automated cookie generation.
   - Session persistence across CLI runs.

2. **JSON-RPC Protocol Client (`FantraxRPCClient`)**:
   - Standardized communication with Fantrax's private backend RPC endpoint (`POST /fx/api/req`).
   - Supports methods: `getLeagueInfo`, `getStandings`, `getRoster`, `getMatchupResults`, `getPlayerData`, etc.

3. **Customizable Scoring Engine (`FantasyScoringEngine`)**:
   - Fully customizable point values for goals, assists, clean sheets, tackles, key passes, intercpetions, saves, goals conceded, red/yellow cards.
   - Computes custom fantasy points on raw player stats or box scores.

4. **Advanced Analytics Suite (`analytics/`)**:
   - **Optimal Lineup Solver (`compute_optimal_lineup_score`)**: Solves for the highest possible points a manager could have scored each Gameweek under valid formation rules.
   - **Manager Efficiency (`calculate_manager_efficiency`)**: Ranks managers by actual points divided by optimal points (bench management efficiency).
   - **Median Standings (`calculate_median_standings`)**: Calculates simulated league standings if extra points were awarded for scoring above the Gameweek median.
   - **Waiver Evaluation (`evaluate_waiver_candidates`)**: Scores free agents based on form, expected minutes, per-90 metrics, and upcoming opponent difficulty.
   - **Per-90 Normalization (`normalize_per_90_stats`)**: Normalizes counting metrics to 90-minute rates for fair player comparisons.

---

## 🛠️ Quick Start & Usage Examples

### 1. Installation & Environment Setup

Ensure dependencies are installed:
```bash
pip install -r requirements.txt
```

Set up your credentials in `soccer/config/.env`:
```env
FANTRAX_LEAGUE_ID=your_league_id_here
FANTRAX_USERNAME=your_email@example.com
FANTRAX_PASSWORD=your_password_here
```

### 2. Fetching League Standings & Rosters

```python
from soccer.fantrax_wrapper import FantraxClient

# Initialize client (automatically loads league_id from environment)
client = FantraxClient()

# Get League Metadata
league_info = client.get_league_info()
print(f"League: {league_info.name} ({league_info.num_teams} teams)")

# Get Current Standings
standings = client.get_standings()
for row in standings:
    print(f"#{row.rank} {row.team_name} - {row.wins}W {row.losses}L {row.draws}D ({row.points} pts)")

# Get Team Roster
roster = client.get_team_roster(team_id="team_123")
for player in roster.players:
    print(f"{player.name} ({player.position} - {player.team}) | Proj: {player.projected_pts}")
```

### 3. Running Manager Efficiency Analysis

```python
from soccer.fantrax_wrapper import FantraxClient

client = FantraxClient()

# Calculate manager bench efficiency across Gameweeks 1 to 20
eff_results = client.get_manager_efficiency(start_period=1, end_period=20)

for mgr in eff_results:
    print(f"{mgr.team_name}: {mgr.efficiency_pct:.1f}% Efficiency ({mgr.actual_pts} / {mgr.optimal_pts} pts)")
```

### 4. Evaluating Free Agent Waiver Candidates

```python
from soccer.fantrax_wrapper import FantraxClient

client = FantraxClient()

# Get recommended waiver targets for Defenders
waivers = client.get_waiver_recommendations(position="D", top_n=10)
for candidate in waivers:
    print(f"{candidate.name} ({candidate.team}) - Score: {candidate.waiver_score:.2f}")
```

---

## 🧪 Testing

Run the automated test suite:
```bash
pytest soccer/tests/
```
