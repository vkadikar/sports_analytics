"""
Reads the fantasy points model's weekly predictions.

soccer/fpts_model writes one league_hub/predictions/gw<NN>.json per gameweek. This reader is separate
from the model so the League Hub and Commish Bot can use predictions without installing scikit-learn.

A prediction isn't a single number. Each player has a points rate per minute and clean sheet points, so
it can be worked out for however long they play. In a predictions file, entry["scoring"] holds both for
each position the player can be scored at, because dual-position players score differently by slot.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PREDICTIONS_DIR = Path(__file__).resolve().parents[1] / "league_hub" / "predictions"

# A clean sheet only counts for a player who was on the pitch this long
CLEAN_SHEET_MINUTES = 60
FULL_GAME_MINUTES = 90


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


def player_prediction(entry: Dict[str, Any], slot: str = "") -> Dict[str, Any]:
    """A player's {"per_min", "clean_sheet", "games", "basis"} when scored at a lineup slot, or their usual
    position. basis is "player", or for someone with no minutes yet, "position_vs_opponent" or "position"."""
    scoring = entry["scoring"].get(slot) or entry["scoring"][entry["position"]]
    return {**scoring, "games": len(entry["fixtures"]), "basis": entry["basis"]}


def points_at_minutes(prediction: Dict[str, Any], minutes_per_game: float) -> float:
    """Predicted fantasy points for a player_prediction if they play this long in each of their games."""
    clean_sheet = prediction["clean_sheet"] if minutes_per_game >= CLEAN_SHEET_MINUTES else 0
    return round(prediction["games"] * (prediction["per_min"] * minutes_per_game + clean_sheet), 2)


def with_predictions(lineup: Dict[str, Any], week: int) -> Dict[str, Any]:
    """A copy of a FantraxClient.get_lineup result with each player's "prediction", where available."""
    data = load_week_predictions(week)
    if data is None:
        return lineup

    def add(player: Dict[str, Any]) -> Dict[str, Any]:
        entry = data["players"].get(player["id"])
        return {**player, "prediction": player_prediction(entry, player.get("slot", "")) if entry else None}

    groups = ("starters", "bench", "injured_reserve")
    return {**lineup, **{group: [add(player) for player in lineup[group]] for group in groups}}
