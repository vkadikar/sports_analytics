"""
Utility functions for Fantrax API Wrapper.
"""

import os
from datetime import datetime
from typing import Optional, Tuple


def load_env_file(env_path: Optional[str] = None) -> bool:
    """Loads environment variables from a .env file (supports 'export KEY=VALUE' and 'KEY=VALUE').

    Searches in provided path, 'soccer/config/.env', or '.env' in current working directory.

    Args:
        env_path: Optional explicit filepath to .env file.

    Returns:
        True if an .env file was found and parsed; False otherwise.
    """
    candidate_paths = []
    if env_path:
        candidate_paths.append(env_path)

    # Search common locations
    candidate_paths.extend([
        os.path.join(os.getcwd(), "soccer", "config", ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "soccer", "config", ".env"),
        os.path.join(os.getcwd(), ".env"),
    ])

    for path in candidate_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[7:].strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        os.environ[k] = v
            return True

    return False


def add_season_year(date_str: str, start_year: int) -> datetime:
    """Assigns the correct calendar year to a date string (e.g. 'Aug 17', 'Jan 12')
    based on Premier League season logic (Aug-Dec -> start_year, Jan-May -> start_year + 1).

    Args:
        date_str: Date string in format '%b %d' (e.g. 'Aug 17').
        start_year: Season start year (e.g. 2024 for 2024-2025 season).

    Returns:
        datetime object with full year assigned.
    """
    date_str_clean = date_str.strip()
    parsed_date = datetime.strptime(f"{date_str_clean} 2000", "%b %d %Y")

    if parsed_date.month >= 8:
        year = start_year
    else:
        year = start_year + 1

    return datetime(year, parsed_date.month, parsed_date.day)


def parse_opponent(opp_str: str) -> Tuple[str, bool]:
    """Parses an opponent string (e.g., '@ARS' or 'BRE') into opponent short name and home indicator.

    Args:
        opp_str: Opponent string from Fantrax game log or match schedule.

    Returns:
        Tuple of (opponent_short_name, home_ind).
        is_home is True if the team is playing at home (no '@'), False if playing away ('@').
    """
    if not opp_str:
        return ("", True)

    opp_clean = opp_str.strip()
    if opp_clean.startswith("@"):
        return (opp_clean[1:], False)
    return (opp_clean, True)
