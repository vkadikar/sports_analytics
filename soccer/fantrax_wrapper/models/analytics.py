"""
Domain models for Analytics, Manager Efficiency, and Waiver Wire Evaluations.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ManagerEfficiency:
    """Represents manager efficiency metrics for a team over a scoring period or season."""

    team_name: str
    actual_fpts: float
    max_fpts_possible: float
    lineup_inefficiency: float  # max_fpts - actual_fpts
    actual_wins: int
    optimal_wins: int
    wins_lost_to_inefficiency: int


@dataclass
class OptimalLineup:
    """Represents the optimal starting XI roster for a team in a given week."""

    week: int
    team_name: str
    actual_score: float
    optimal_score: float
    optimal_starters: List[str] = field(default_factory=list)
    benched_starters: List[str] = field(default_factory=list)


@dataclass
class WaiverCandidate:
    """Represents a free agent player evaluated for waiver wire pickup."""

    player_id: str
    player_name: str
    team: str
    position: str
    games_played: int
    season_minutes: int
    last_week_minutes: int
    season_fpts: float
    avg_fpts_per_game: float
    fpts_per_90: float
    opponent: str = ""
    opponent_rank: Optional[int] = None
