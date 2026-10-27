"""
Fantrax API Wrapper for Fantasy Premier League.

A clean, modular, fully typed Python wrapper for fetching and analyzing Fantrax league data.
"""

from .client import FantraxClient
from .session import FantraxSessionManager
from .rpc import FantraxRPCClient
from .scoring import FantasyScoringEngine, STAT_NAMES
from .utils import add_season_year, parse_opponent, load_env_file
from .models import (
    LeagueInfo,
    StandingRow,
    WeeklyMatchup,
    Team,
    TeamRoster,
    RosterRow,
    PlayerSummary,
    PlayerProfile,
    GameLogEntry,
    ManagerEfficiency,
    OptimalLineup,
    WaiverCandidate,
)
from .analytics import (
    compute_optimal_lineup_score,
    calculate_manager_efficiency,
    calculate_median_standings,
    calculate_optimal_standings,
    compare_standings_vs_optimal,
    evaluate_waiver_candidates,
    normalize_per_90_stats,
    compute_positional_opponent_averages,
)

__version__ = "1.0.0"

__all__ = [
    "FantraxClient",
    "FantraxSessionManager",
    "FantraxRPCClient",
    "FantasyScoringEngine",
    "STAT_NAMES",
    "add_season_year",
    "parse_opponent",
    "load_env_file",
    "LeagueInfo",
    "StandingRow",
    "WeeklyMatchup",
    "Team",
    "TeamRoster",
    "RosterRow",
    "PlayerSummary",
    "PlayerProfile",
    "GameLogEntry",
    "ManagerEfficiency",
    "OptimalLineup",
    "WaiverCandidate",
    "compute_optimal_lineup_score",
    "calculate_manager_efficiency",
    "calculate_median_standings",
    "calculate_optimal_standings",
    "compare_standings_vs_optimal",
    "evaluate_waiver_candidates",
    "normalize_per_90_stats",
    "compute_positional_opponent_averages",
]
