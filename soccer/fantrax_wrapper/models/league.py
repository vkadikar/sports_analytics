"""
Domain models for League, Matchup, and Standings.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd


@dataclass
class StandingRow:
    """Represents a team's standing row in the league table."""

    team_id: str
    team_name: str
    wins: int
    draws: int
    losses: int
    points: int
    fpts_for: float
    fpts_against: float
    avg_fpts_for: float
    avg_fpts_against: float
    std_fpts_for: float

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.draws}-{self.losses}"


@dataclass
class WeeklyMatchup:
    """Represents a weekly head-to-head fantasy matchup."""

    week: int
    matchup_id: int
    home_team_id: str
    home_team_name: str
    home_score: float
    away_team_id: str
    away_team_name: str
    away_score: float

    @property
    def winner_team_id(self) -> Optional[str]:
        if self.home_score > self.away_score:
            return self.home_team_id
        elif self.away_score > self.home_score:
            return self.away_team_id
        return None  # Draw


@dataclass
class LeagueInfo:
    """Represents core Fantrax league metadata."""

    league_id: str
    name: str = ""
    season: int = 2025
    current_week: int = 1
    total_weeks: int = 38
    teams: List[str] = field(default_factory=list)
