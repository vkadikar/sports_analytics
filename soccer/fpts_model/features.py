"""
Feature engineering for the fantasy points model.

Turns one season of player game logs into one row per player per game. Past seasons are built
the same way, one season at a time, so form and standings start fresh each year. Features are
point in time: a row in gameweek N depends only on games played before gameweek N, so
results from a week, or any later one, can never reach that week's features.
"""

from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# Stats with rolling per-minute features
ROLLING_STATS = [
    "g", "kp", "at", "sot", "tkw", "dis", "acnc", "int", "clr",
    "cos", "bs", "aer", "gao", "cs", "sv", "pks", "hcs", "sm",
]

# Scored stats the model predicts from fixture context alone
CONTEXT_ONLY_STATS = ["yc", "rc", "pkm", "pkd", "og"]

TARGET_STATS = ROLLING_STATS + CONTEXT_ONLY_STATS

CATEGORICAL_FEATURES = ["player_id", "team", "opp", "position"]

CONTEXT_FEATURES = [
    "player_id", "team", "opp", "team_week_standing",
    "team_week_standing_opp", "position", "is_away",
]


def gameweek_of(day: date, gw_dates: Dict[int, Dict[str, date]]) -> Optional[int]:
    """The Fantrax gameweek whose date range contains a day, or None."""
    for week, dates in gw_dates.items():
        if dates["start"] <= day <= dates["end"]:
            return week
    return None


def clean_game_logs(game_logs: pd.DataFrame, gw_dates: Dict[int, Dict[str, date]]) -> pd.DataFrame:
    """Normalizes raw Fantrax game logs and assigns each game its Fantrax gameweek.

    Args:
        game_logs: One row per player game from a single season, with columns player_id,
            position, Date, Team, Opp ('@' prefix for away), Score ('W 4-0'), Min and the box
            score stats. Fixtures to predict have a blank Score and stats.
        gw_dates: Fantrax gameweek date ranges, from FantraxClient.get_gameweek_dates.

    Returns:
        DataFrame with lowercase columns, numeric stats, and matchweek, played, is_away and minutes columns.
    """
    df = game_logs.copy()
    df.columns = [col.lower() for col in df.columns]

    if "season" in df.columns and df["season"].nunique() > 1:
        raise ValueError("game_logs must cover a single season")

    df["season"] = gw_dates[min(gw_dates)]["start"].year
    df["date"] = pd.to_datetime(df["date"])
    df["matchweek"] = df["date"].map(lambda day: gameweek_of(day.date(), gw_dates))
    if df["matchweek"].isna().any():
        raise ValueError(f"Games outside every gameweek: {sorted(df.loc[df['matchweek'].isna(), 'date'].unique())}")
    df["matchweek"] = df["matchweek"].astype(int)

    # A gameweek 1 with nothing played yet has fixtures but no scores at all
    df = df.reindex(columns=df.columns.union(["score"], sort=False))
    df["played"] = df["score"].notna()
    df["is_away"] = df["opp"].str.startswith("@").astype(int)
    df["opp"] = df["opp"].str.replace("@", "")

    # Goalkeeper logs report goals conceded as GA, outfield logs as GAO
    numeric = TARGET_STATS + ["ga", "min"]
    df = df.reindex(columns=df.columns.union(numeric, sort=False))
    df["gao"] = df["gao"].fillna(df["ga"])
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce").fillna(0)
    df["minutes"] = df["min"].astype(int)

    return df.sort_values(["matchweek", "date", "player_id"], ascending=[True, True, False]).reset_index(drop=True)


def _add_rolling_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Adds per-minute rates from each player's previous game and season to date."""
    players = df["player_id"]
    last_minutes = df.groupby("player_id")["minutes"].shift(1).fillna(0)
    season_minutes = last_minutes.groupby(players).cumsum()

    rates = {}
    for stat in ROLLING_STATS:
        last = df.groupby("player_id")[stat].shift(1).fillna(0)
        season = last.groupby(players).cumsum()
        rates[f"{stat}_per_min_gameweek"] = last / last_minutes
        rates[f"{stat}_per_min_season"] = season / season_minutes
    rates = pd.DataFrame(rates)

    # A second unplayed fixture would otherwise treat the first one as a 0-minute game
    unplayed = df.loc[~df["played"], "player_id"]
    repeats = unplayed[unplayed.duplicated()].index
    blanked = rates.copy()
    blanked.loc[repeats] = np.nan
    rates.loc[repeats] = blanked.groupby(players).ffill().loc[repeats]

    return pd.concat([df, rates], axis=1)


def _add_positional_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the trimmed mean per-minute rates of each position facing each opponent in earlier gameweeks."""
    rate_cols = [col for col in df.columns if "per_min" in col]

    rows = []
    for (opp, position), group in df.groupby(["opp", "position"]):
        for week in group["matchweek"].unique():
            earlier = group.loc[group["matchweek"] < week, rate_cols]
            trimmed = earlier.where(earlier.ge(earlier.quantile(0.05)) & earlier.le(earlier.quantile(0.95)))
            rows.append({"opp": opp, "position": position, "matchweek": week, **trimmed.mean().to_dict()})

    averages = pd.DataFrame(rows).rename(columns={col: f"positional_avg_{col}" for col in rate_cols})
    return df.merge(averages, on=["opp", "position", "matchweek"])


def _league_standings(df: pd.DataFrame) -> pd.DataFrame:
    """Each club's league position going into each gameweek, from results in earlier gameweeks."""
    games = df[df["played"]].drop_duplicates(["team", "date"])
    scores = games["score"].astype(str)
    goals = scores.str.extract(r"(\d+)-(\d+)").astype(int)
    results = pd.DataFrame({
        "team": games["team"],
        "matchweek": games["matchweek"],
        "table_points": scores.str[0].map({"W": 3, "T": 1}).fillna(0),
        "goals_for": goals[0],
        "goals_against": goals[1],
    })

    rows = []
    for week in df["matchweek"].unique():
        earlier = results[results["matchweek"] < week]
        table = earlier.groupby("team")[["table_points", "goals_for", "goals_against"]].sum()
        table = table.reindex(df["team"].unique(), fill_value=0).rename_axis("team").reset_index()
        table["goal_differential"] = table["goals_for"] - table["goals_against"]
        table = table.sort_values(
            ["table_points", "goal_differential", "goals_for", "goals_against", "team"],
            ascending=[False, False, False, True, True],
        )
        rows.append(pd.DataFrame({"team": table["team"], "matchweek": week, "team_week_standing": range(1, len(table) + 1)}))
    return pd.concat(rows, ignore_index=True)


def _add_league_standings(df: pd.DataFrame) -> pd.DataFrame:
    """Adds each team's and opponent's league position going into the gameweek."""
    standings = _league_standings(df)
    opponents = standings.rename(columns={"team": "opp", "team_week_standing": "team_week_standing_opp"})
    return df.merge(standings, on=["matchweek", "team"]).merge(opponents, on=["matchweek", "opp"])


def build_features(game_logs: pd.DataFrame, gw_dates: Dict[int, Dict[str, date]]) -> pd.DataFrame:
    """Builds the model's feature table from raw game logs.

    Args:
        game_logs: Raw game logs, as described in clean_game_logs.
        gw_dates: Fantrax gameweek date ranges.

    Returns:
        DataFrame with one row per player game and the features in feature_columns.
    """
    df = clean_game_logs(game_logs, gw_dates)
    df = _add_rolling_stats(df)
    df = _add_positional_averages(df)
    df = _add_league_standings(df)

    # A player's first game, games after a DNP and first meetings with an opponent have undefined rates
    rate_cols = [col for col in df.columns if "per_min" in col]
    df[rate_cols] = df[rate_cols].fillna(0)
    return df


def feature_columns(stat: str) -> List[str]:
    """Returns the columns used to predict a stat, in model order."""
    if stat not in ROLLING_STATS:
        return list(CONTEXT_FEATURES)
    return CONTEXT_FEATURES + [
        f"{stat}_per_min_gameweek",
        f"{stat}_per_min_season",
        f"positional_avg_{stat}_per_min_gameweek",
        f"positional_avg_{stat}_per_min_season",
    ]
