"""
Reads the fantasy points model's weekly predictions.

soccer/fpts_model writes one league_hub/predictions/gw<NN>.json per gameweek. This reader is separate
from the model so the League Hub and Commish Bot can use predictions without installing scikit-learn.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PREDICTIONS_DIR = Path(__file__).resolve().parents[1] / "league_hub" / "predictions"


def predictions_path(week: int) -> Path:
    """Where a gameweek's predictions are stored."""
    return PREDICTIONS_DIR / f"gw{week:02d}.json"


def available_prediction_weeks() -> List[int]:
    """Gameweeks that have predictions, in order."""
    return sorted(int(path.stem[2:]) for path in PREDICTIONS_DIR.glob("gw*.json"))


def load_week_predictions(week: int) -> Optional[Dict[str, Any]]:
    """A gameweek's predictions file, or None if it has none. Its "players" map is keyed by Fantrax player ID."""
    path = predictions_path(week)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def predicted_points(entry: Dict[str, Any], slot: str = "") -> float:
    """A player's predicted points. Dual-position players score differently at the slot they start in."""
    return entry.get("by_position", {}).get(slot, entry["fpts"])


def with_predictions(lineup: Dict[str, Any], week: int) -> Dict[str, Any]:
    """A copy of a FantraxClient.get_lineup result with each player's "predicted" points, where available."""
    data = load_week_predictions(week)
    if data is None:
        return lineup

    def add(player: Dict[str, Any]) -> Dict[str, Any]:
        entry = data["players"].get(player["id"])
        return {**player, "predicted": predicted_points(entry, player.get("slot", "")) if entry else None}

    groups = ("starters", "bench", "injured_reserve")
    return {**lineup, **{group: [add(player) for player in lineup[group]] for group in groups}}
