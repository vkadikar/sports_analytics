"""
Stat Normalization and Positional Opponent Baseline Calculators.
"""

from typing import List
import pandas as pd


def normalize_per_90_stats(
    df: pd.DataFrame,
    stat_columns: List[str],
    minutes_col: str = "minutes",
) -> pd.DataFrame:
    """Calculates per-minute and per-90 metrics for a set of counting stats.

    Args:
        df: DataFrame containing raw match performance rows.
        stat_columns: List of stat column names to convert to per-90.
        minutes_col: Column name representing minutes played.

    Returns:
        DataFrame augmented with per_min and per_90 columns.
    """
    res = df.copy()
    mins = res[minutes_col].astype(float).replace(0, 1.0)

    for col in stat_columns:
        if col in res.columns:
            res[f"{col}_per_min"] = (res[col].astype(float) / mins).round(3)
            res[f"{col}_per_90"] = (res[f"{col}_per_min"] * 90.0).round(2)

    return res


def compute_positional_opponent_averages(
    df: pd.DataFrame,
    per90_columns: List[str],
    opp_col: str = "opp",
    pos_col: str = "position",
    trim_lower: float = 0.05,
    trim_upper: float = 0.95,
) -> pd.DataFrame:
    """Computes trimmed mean positional average stats conceded/allowed by each opponent team.

    Args:
        df: DataFrame containing player game logs.
        per90_columns: List of per-90 columns to average.
        opp_col: Opponent team column name.
        pos_col: Player position column name.
        trim_lower: Lower quantile cutoff for trimmed mean.
        trim_upper: Upper quantile cutoff for trimmed mean.

    Returns:
        DataFrame grouped by [opp, position] with positional average baselines.
    """
    def trimmed_mean(s: pd.Series) -> float:
        valid = s.dropna()
        if valid.empty:
            return 0.0
        q_low = valid.quantile(trim_lower)
        q_high = valid.quantile(trim_upper)
        filtered = valid[valid.between(q_low, q_high)]
        return round(filtered.mean(), 2) if not filtered.empty else round(valid.mean(), 2)

    cols_present = [c for c in per90_columns if c in df.columns]
    grouped = (
        df.groupby([opp_col, pos_col])[cols_present]
        .apply(lambda g: g.apply(trimmed_mean))
        .reset_index()
    )
    grouped.rename(
        columns={col: f"positional_avg_{col}" for col in cols_present},
        inplace=True
    )
    return grouped
