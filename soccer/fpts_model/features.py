"""
Feature engineering for the fantasy points model.

Turns one season of player game logs into one row per player per gameweek. Every
feature describes what was known before kickoff, so upcoming fixtures can be scored.
"""

from statistics import mode
from typing import List

import numpy as np
import pandas as pd


# Stats with rolling per-minute and per-90 features
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


def clean_game_logs(game_logs: pd.DataFrame) -> pd.DataFrame:
    """Normalizes raw Fantrax game logs and assigns each game a matchweek.

    Args:
        game_logs: One row per player game from a single season, with columns player_id,
            position, Date, Team, Opp ('@' prefix for away), Score ('W 4-0'), Min, GA and
            the box score stats. To predict a gameweek, include a row for each player's
            fixture in it, with Score 'L 0-0' and the stats left blank.

    Returns:
        DataFrame with lowercase columns, numeric stats, and matchweek, is_away and minutes columns.
    """
    df = game_logs.copy()
    df.columns = [col.lower() for col in df.columns]

    if "season" in df.columns and df["season"].nunique() > 1:
        raise ValueError("game_logs must cover a single season")

    df["date"] = pd.to_datetime(df["date"])
    df["matchweek"] = df.groupby("team")["date"].rank(method="dense").astype(int)
    df["is_away"] = df["opp"].str.startswith("@").astype(int)
    df["opp"] = df["opp"].str.replace("@", "")

    # Goalkeeper logs report goals conceded as GA, outfield logs as GAO
    df["gao"] = df["gao"].fillna(df["ga"])

    numeric = TARGET_STATS + ["min"]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce").fillna(0)
    df["minutes"] = df["min"].astype(int)

    return df.sort_values(["matchweek", "player_id"], ascending=[True, False]).reset_index(drop=True)


def _add_rolling_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Adds per-minute and per-90 rates from each player's previous game and season to date."""
    players = df["player_id"]
    last_minutes = df.groupby("player_id")["minutes"].shift(1).fillna(0)
    season_minutes = last_minutes.groupby(players).cumsum()

    rates = {}
    for stat in ROLLING_STATS:
        last = df.groupby("player_id")[stat].shift(1).fillna(0)
        season = last.groupby(players).cumsum()
        per_min_gameweek = (last / last_minutes).round(3)
        per_min_season = (season / season_minutes).round(3)
        rates[f"{stat}_per_min_gameweek"] = per_min_gameweek
        rates[f"{stat}_per_min_season"] = per_min_season
        rates[f"{stat}_per_90_gameweek"] = per_min_gameweek * 90
        rates[f"{stat}_per_90_season"] = per_min_season * 90

    return pd.concat([df, pd.DataFrame(rates)], axis=1)


def _add_positional_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the trimmed mean per-90 rates of each position facing each opponent."""
    def trimmed_mean(s: pd.Series) -> float:
        return s[s.between(s.quantile(0.05), s.quantile(0.95))].mean()

    per90_cols = [col for col in df.columns if "per_90" in col]
    averages = (
        df.groupby(["opp", "position"])[per90_cols]
        .apply(lambda group: group.apply(trimmed_mean))
        .reset_index()
        .rename(columns={col: f"positional_avg_{col}" for col in per90_cols})
    )
    return df.merge(averages, on=["opp", "position"])


def _add_league_standings(df: pd.DataFrame) -> pd.DataFrame:
    """Adds each team's and opponent's league position going into the matchweek."""
    last_score = df.groupby("player_id")["score"].shift(1).fillna("L 0-0")
    result = last_score.str[0]
    goals = last_score.str.extract(r"(\d+)-(\d+)").astype(int)

    table = df[["player_id", "matchweek", "team"]].assign(
        result_points=np.where(result == "W", 3, np.where(result == "T", 1, 0)),
        goals_for=goals[0],
        goals_against=goals[1],
    )
    # Players missing from a team's previous game carry older results, so take the majority
    weekly_points = (
        table.groupby(["team", "matchweek"])["result_points"]
        .agg(lambda points: mode(list(points)))
        .groupby("team")
        .cumsum()
        .rename("table_points")
        .reset_index()
    )
    table = table.merge(weekly_points, on=["team", "matchweek"])
    table["total_goals_for"] = table.groupby("player_id")["goals_for"].cumsum()
    table["total_goals_against"] = table.groupby("player_id")["goals_against"].cumsum()
    table["goal_differential"] = table["total_goals_for"] - table["total_goals_against"]

    standings = (
        table.groupby(["matchweek", "team"], as_index=False)
        .first()
        .sort_values(
            ["matchweek", "table_points", "goal_differential", "total_goals_for", "total_goals_against"],
            ascending=[True, False, False, False, True],
        )
    )
    standings["team_week_standing"] = standings.groupby("matchweek").cumcount().add(1)
    standings = standings[["matchweek", "team", "team_week_standing"]]

    df = df.merge(standings, on=["matchweek", "team"])
    opponents = standings.rename(columns={"team": "opp", "team_week_standing": "team_week_standing_opp"})
    return df.merge(opponents, on=["matchweek", "opp"])


def build_features(game_logs: pd.DataFrame) -> pd.DataFrame:
    """Builds the model's feature table from raw game logs.

    Args:
        game_logs: Raw game logs, as described in clean_game_logs.

    Returns:
        DataFrame with one row per player per matchweek and the features in feature_columns.
    """
    df = clean_game_logs(game_logs)
    df = _add_rolling_stats(df)
    df = _add_positional_averages(df)
    df = _add_league_standings(df)

    # A player's first game and games after a DNP have undefined rates
    rate_cols = [col for col in df.columns if "per_min" in col or "per_90" in col]
    df[rate_cols] = df[rate_cols].fillna(0)
    return df


def feature_columns(stat: str) -> List[str]:
    """Returns the columns used to predict a stat, in model order."""
    if stat not in ROLLING_STATS:
        return list(CONTEXT_FEATURES)
    return CONTEXT_FEATURES + [
        f"{stat}_per_min_gameweek",
        f"{stat}_per_min_season",
        f"{stat}_per_90_gameweek",
        f"{stat}_per_90_season",
        f"positional_avg_{stat}_per_90_gameweek",
        f"positional_avg_{stat}_per_90_season",
    ]
