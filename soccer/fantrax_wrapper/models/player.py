"""
Domain models for Players, Profiles, and Game Logs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class GameLogEntry:
    """Represents a player's box score performance in a single gameweek match."""

    player_id: str
    player_name: str
    date: Optional[datetime]
    team: str
    opponent: str
    is_home: bool
    score_str: str
    minutes: int
    fpts: float
    calc_fpts: float = 0.0
    afpts: float = 0.0
    stats: Dict[str, float] = field(default_factory=dict)


@dataclass
class PlayerSummary:
    """Represents high-level player metadata from player stats table."""

    scorer_id: str
    name: str
    team_short_name: str
    team_name: str
    position_short: str  # 'G', 'D', 'M', 'F'
    next_match: str = ""
    opponent_short_name: str = ""
    opponent_name: str = ""
    fpts: float = 0.0
    fpts_per_game: float = 0.0
    rostered_pct: float = 0.0
    url_name: str = ""


@dataclass
class PlayerProfile:
    """Represents detailed player profile including game logs and latest news."""

    player_id: str
    name: str
    position: str
    team: str
    game_log: List[GameLogEntry] = field(default_factory=list)
    latest_news: str = ""
