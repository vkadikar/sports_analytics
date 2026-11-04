"""
Scores the stored predictions against what happened, at the minutes each player actually played.

This measures how well the model read a player's output, not whether it knew how long they'd play.
Players who didn't play aren't scored. The baseline is the player's own points per minute so far this
season at the same minutes. Players without an earlier game have no baseline, so they're reported apart.

    python3 -m fpts_model.evaluate
"""

from typing import List

import numpy as np
import pandas as pd
from fantrax_wrapper import FantasyScoringEngine, available_prediction_weeks, load_week_predictions, player_prediction, points_at_minutes

from .data import GAME_LOGS_DIR
from .features import TARGET_STATS


def load_scored_games() -> pd.DataFrame:
    """Every stored game with its actual fantasy points."""
    engine = FantasyScoringEngine()
    logs = pd.concat(
        [pd.read_csv(path, dtype={"player_id": str}).assign(week=int(path.stem[2:])) for path in sorted(GAME_LOGS_DIR.glob("gw*.csv"))],
        ignore_index=True,
    )
    logs[TARGET_STATS] = logs[TARGET_STATS].fillna(0)
    logs["actual"] = [
        engine.calculate_fantasy_score({stat: row[stat] for stat in TARGET_STATS}, row["position"])
        for row in logs.to_dict("records")
    ]
    return logs


def prediction_errors(games: pd.DataFrame, weeks: List[int]) -> pd.DataFrame:
    """One row per played game with the model's and the baseline's points at the actual minutes."""
    rows = []
    for week in weeks:
        document = load_week_predictions(week)
        earlier = games[games["week"] < week].groupby("player_id")[["actual", "Min"]].sum()
        for game in games[games["week"] == week].to_dict("records"):
            entry = document["players"].get(game["player_id"])
            if entry is None or game["Min"] <= 0:
                continue
            has_history = game["player_id"] in earlier.index
            history = earlier.loc[game["player_id"]] if has_history else None
            prediction = player_prediction(entry)
            rows.append({
                "week": week,
                "position": game["position"],
                "minutes": game["Min"],
                "actual": game["actual"],
                "model": points_at_minutes(prediction, game["Min"] / prediction["games"]),
                "has_history": has_history,
                "baseline": history["actual"] / history["Min"] * game["Min"] if has_history else np.nan,
            })
    return pd.DataFrame(rows)


def summarize(errors: pd.DataFrame) -> pd.Series:
    """Error measures for the model and the baseline over a set of games."""
    model, baseline, actual = errors["model"], errors["baseline"], errors["actual"]
    return pd.Series({
        "games": len(errors),
        "mae_model": (model - actual).abs().mean(),
        "mae_base": (baseline - actual).abs().mean(),
        "rmse_model": np.sqrt(((model - actual) ** 2).mean()),
        "rmse_base": np.sqrt(((baseline - actual) ** 2).mean()),
        "corr_model": model.corr(actual),
        "corr_base": baseline.corr(actual),
        "bias_model": (model - actual).mean(),
        "bias_base": (baseline - actual).mean(),
    }).round(3)


def main() -> int:
    games = load_scored_games()
    weeks = [week for week in available_prediction_weeks() if week in set(games["week"])]
    all_errors = prediction_errors(games, weeks)
    errors = all_errors[all_errors["has_history"]]
    print("All games with a baseline\n", summarize(errors).to_string())
    debuts = all_errors[~all_errors["has_history"]]
    print(f"\nPlayers without an earlier game: {len(debuts)} games, average error {(debuts['model'] - debuts['actual']).abs().mean():.3f}, bias {(debuts['model'] - debuts['actual']).mean():+.3f}")
    print("\nBy gameweek\n", errors.groupby("week")[errors.columns.tolist()].apply(summarize).to_string())
    print("\nBy position\n", errors.groupby("position")[errors.columns.tolist()].apply(summarize).to_string())
    buckets = pd.cut(errors["minutes"], [0, 30, 59, 90], labels=["1-30", "31-59", "60-90"])
    print("\nBy minutes played\n", errors.groupby(buckets, observed=True)[errors.columns.tolist()].apply(summarize).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
