"""
Manager Efficiency & Optimal Lineup Analytics Engine.
"""

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


def compute_optimal_lineup_score(
    g_scores: List[float],
    d_scores: List[float],
    m_scores: List[float],
    f_scores: List[float],
) -> float:
    """Computes the maximum possible fantasy points (max_points_for) for a roster in a gameweek.

    Selection rules:
    - Exactly 1 Goalkeeper
    - Minimum 3 Defenders, 2 Midfielders, 1 Forward
    - Greedily fills remaining 4 starter spots up to 11 total starters:
      - Max 5 Defenders total
      - Max 5 Midfielders total
      - Max 3 Forwards total

    Args:
        g_scores: List of fantasy scores for goalkeepers on roster.
        d_scores: List of fantasy scores for defenders on roster.
        m_scores: List of fantasy scores for midfielders on roster.
        f_scores: List of fantasy scores for forwards on roster.

    Returns:
        Max possible fantasy score total.
    """
    sorted_g = sorted(g_scores)
    sorted_d = sorted(d_scores)
    sorted_m = sorted(m_scores)
    sorted_f = sorted(f_scores)

    # Base mandatory starting spots
    top_g = sorted_g[-1:] if sorted_g else [0.0]
    top_d = sorted_d[-3:] if len(sorted_d) >= 3 else sorted_d[:]
    top_m = sorted_m[-2:] if len(sorted_m) >= 2 else sorted_m[:]
    top_f = sorted_f[-1:] if len(sorted_f) >= 1 else sorted_f[:]

    # Remaining bench pools
    rem_d = sorted_d[:-len(top_d)] if len(sorted_d) > len(top_d) else []
    rem_m = sorted_m[:-len(top_m)] if len(sorted_m) > len(top_m) else []
    rem_f = sorted_f[:-len(top_f)] if len(sorted_f) > len(top_f) else []

    # Fill up to 11 total starters (1 GK + 10 Outfielders)
    for _ in range(4):
        total_starters = 1 + len(top_d) + len(top_m) + len(top_f)
        if total_starters >= 11:
            break

        can_add_d = len(rem_d) > 0 and len(top_d) < 5
        can_add_m = len(rem_m) > 0 and len(top_m) < 5
        can_add_f = len(rem_f) > 0 and len(top_f) < 3

        candidates = []
        if can_add_d:
            candidates.append((rem_d[-1], 'D'))
        if can_add_m:
            candidates.append((rem_m[-1], 'M'))
        if can_add_f:
            candidates.append((rem_f[-1], 'F'))

        if not candidates:
            break

        # Pick highest scoring available player
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, pos = candidates[0]

        if pos == 'D':
            top_d.append(rem_d.pop())
        elif pos == 'M':
            top_m.append(rem_m.pop())
        elif pos == 'F':
            top_f.append(rem_f.pop())

    return round(sum(top_g + top_d + top_m + top_f), 2)


def calculate_manager_efficiency(matchup_df: pd.DataFrame) -> pd.DataFrame:
    """Calculates lineup inefficiency metrics for each team across completed matchweeks.

    Args:
        matchup_df: DataFrame containing 'week', 'team', 'score', and 'max_points_for'.

    Returns:
        DataFrame summarizing average lineup inefficiency and total missed points per team.
    """
    df = matchup_df.copy()
    df["lineup_inefficiency"] = df["max_points_for"] - df["score"]
    df["weighted_lineup_inefficiency"] = df["lineup_inefficiency"] / np.where(df["score"] == 0, 1, df["score"])

    summary = df.groupby("team").agg(
        avg_inefficiency=("lineup_inefficiency", "mean"),
        total_missed_points=("lineup_inefficiency", "sum"),
        avg_actual_score=("score", "mean"),
        avg_max_score=("max_points_for", "mean"),
    ).round(2).sort_values("avg_inefficiency")

    return summary


def calculate_median_standings(matchup_df: pd.DataFrame) -> pd.DataFrame:
    """Calculates alternative league standings based on performance against weekly league median score.

    Args:
        matchup_df: DataFrame containing 'week', 'team', 'score', and 'opponent_score'.

    Returns:
        DataFrame containing standings against weekly medians.
    """
    df = matchup_df.copy()
    weekly_medians = df.groupby("week")["score"].median()
    df["weekly_median"] = df["week"].map(weekly_medians)

    df["result_vs_median"] = np.where(
        df["score"] > df["weekly_median"], "W",
        np.where(df["score"] < df["weekly_median"], "L", "D")
    )

    standings = pd.DataFrame()
    standings["wins"] = df.groupby("team")["result_vs_median"].apply(lambda s: (s == "W").sum())
    standings["draws"] = df.groupby("team")["result_vs_median"].apply(lambda s: (s == "D").sum())
    standings["losses"] = df.groupby("team")["result_vs_median"].apply(lambda s: (s == "L").sum())
    standings["points"] = standings["wins"] * 3 + standings["draws"]
    standings["fpts_for"] = df.groupby("team")["score"].sum().round(2)
    standings["fpts_against"] = df.groupby("team")["opponent_score"].sum().round(2)
    standings["record"] = standings["wins"].astype(str) + "-" + standings["draws"].astype(str) + "-" + standings["losses"].astype(str)

    return standings.sort_values(["points", "fpts_for"], ascending=False)


def compute_optimal_team_lineup(
    roster_players: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Given a list of player dicts containing 'player_name', 'position', 'score', returns optimal starting XI and bench.

    Rules:
    - 1 Goalkeeper (highest scoring)
    - Mandatory: 3 Defenders, 2 Midfielders, 1 Forward
    - Greedily fills remaining 4 starter spots up to 11 total starters (Max 5 D, Max 5 M, Max 3 F)
    - Remaining players placed on Bench / Reserves

    Args:
        roster_players: List of dicts with keys 'player_name', 'position', 'score'.

    Returns:
        Dict with keys 'starters', 'bench', 'optimal_score'.
    """
    g_pool = [p for p in roster_players if str(p.get("position", "")).startswith("G")]
    d_pool = [p for p in roster_players if str(p.get("position", "")).startswith("D")]
    m_pool = [p for p in roster_players if str(p.get("position", "")).startswith("M")]
    f_pool = [p for p in roster_players if str(p.get("position", "")).startswith("F")]

    # Sort each pool by score descending
    g_sorted = sorted(g_pool, key=lambda x: x.get("score", 0.0), reverse=True)
    d_sorted = sorted(d_pool, key=lambda x: x.get("score", 0.0), reverse=True)
    m_sorted = sorted(m_pool, key=lambda x: x.get("score", 0.0), reverse=True)
    f_sorted = sorted(f_pool, key=lambda x: x.get("score", 0.0), reverse=True)

    starters = []
    bench = []

    # Mandatory picks
    if g_sorted:
        starters.append(g_sorted[0])
        bench.extend(g_sorted[1:])

    top_d = d_sorted[:3]
    rem_d = d_sorted[3:]
    starters.extend(top_d)

    top_m = m_sorted[:2]
    rem_m = m_sorted[2:]
    starters.extend(top_m)

    top_f = f_sorted[:1]
    rem_f = f_sorted[1:]
    starters.extend(top_f)

    # Greedily fill up to 11 total starters
    for _ in range(4):
        if len(starters) >= 11:
            break

        candidates = []
        if rem_d and len([s for s in starters if str(s.get("position", "")).startswith("D")]) < 5:
            candidates.append((rem_d[0], 'D'))
        if rem_m and len([s for s in starters if str(s.get("position", "")).startswith("M")]) < 5:
            candidates.append((rem_m[0], 'M'))
        if rem_f and len([s for s in starters if str(s.get("position", "")).startswith("F")]) < 3:
            candidates.append((rem_f[0], 'F'))

        if not candidates:
            break

        candidates.sort(key=lambda x: x[0].get("score", 0.0), reverse=True)
        best_player, pos = candidates[0]
        starters.append(best_player)

        if pos == 'D':
            rem_d.pop(0)
        elif pos == 'M':
            rem_m.pop(0)
        elif pos == 'F':
            rem_f.pop(0)

    # Remaining available players go to bench
    bench.extend(rem_d)
    bench.extend(rem_m)
    bench.extend(rem_f)

    optimal_score = round(sum(p.get("score", 0.0) for p in starters), 2)
    return {
        "starters": starters,
        "bench": bench,
        "optimal_score": optimal_score,
    }
