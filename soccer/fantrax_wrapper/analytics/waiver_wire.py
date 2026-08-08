"""
Waiver Wire Evaluation & Free Agent Recommendation Engine.
"""

from typing import List, Optional
import pandas as pd


def evaluate_waiver_candidates(
    df_player_stats: pd.DataFrame,
    rostered_player_names: List[str],
    current_week: int,
    min_last_week_minutes: int = 45,
    exclude_goalkeepers: bool = True,
) -> pd.DataFrame:
    """Filters and ranks available free agents on waiver wire.

    Args:
        df_player_stats: DataFrame containing player game logs and stat aggregations.
        rostered_player_names: List of names of players currently rostered by any league team.
        current_week: Current matchweek integer.
        min_last_week_minutes: Minimum minutes played in the most recent completed week.
        exclude_goalkeepers: Whether to exclude goalkeepers from waiver candidate list.

    Returns:
        DataFrame of ranked waiver candidates with stats per game and per 90.
    """
    df = df_player_stats.copy()

    name_col = "player_name" if "player_name" in df.columns else ("name" if "name" in df.columns else None)
    if name_col:
        waivers = df[~df[name_col].isin(rostered_player_names)].copy()
    else:
        waivers = df.copy()

    if exclude_goalkeepers and "position" in waivers.columns:
        waivers = waivers[waivers["position"] != "G"]

    # Filter by last week minutes if column exists
    if "last_week_minutes" in waivers.columns:
        waivers = waivers[waivers["last_week_minutes"] >= min_last_week_minutes]

    # Calculate average FPts per game if games_played exists
    if "games_played" in waivers.columns and "season_fpts" in waivers.columns:
        waivers["avg_fpts_per_game"] = (waivers["season_fpts"] / waivers["games_played"].replace(0, 1)).round(2)

    sort_col = "avg_fpts_per_game" if "avg_fpts_per_game" in waivers.columns else "fpts"
    if sort_col in waivers.columns:
        waivers = waivers.sort_values(sort_col, ascending=False)

    return waivers.reset_index(drop=True)
