"""
Domain models for Teams, Rosters, and Lineup positions.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RosterRow:
    """Represents a single player entry in a team roster for a given scoring period."""

    player_id: str
    player_name: str
    position_short: str  # 'G', 'D', 'M', 'F', 'Res', 'IR'
    is_starter: bool
    is_reserve: bool
    is_injured_reserve: bool
    points: float = 0.0


@dataclass
class TeamRoster:
    """Represents a team's complete roster for a given week."""

    team_id: str
    team_name: str
    week: int
    goalkeeper: Optional[RosterRow] = None
    defenders: List[RosterRow] = field(default_factory=list)
    midfielders: List[RosterRow] = field(default_factory=list)
    forwards: List[RosterRow] = field(default_factory=list)
    reserves: List[RosterRow] = field(default_factory=list)
    injured_reserve: List[RosterRow] = field(default_factory=list)

    @property
    def starters(self) -> List[RosterRow]:
        starters_list = []
        if self.goalkeeper:
            starters_list.append(self.goalkeeper)
        starters_list.extend(self.defenders)
        starters_list.extend(self.midfielders)
        starters_list.extend(self.forwards)
        return starters_list


@dataclass
class Team:
    """Represents a fantasy team in the league."""

    id: str
    name: str
    short_name: str = ""
