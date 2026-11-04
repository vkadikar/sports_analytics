"""
Trains and stores the model for every gameweek that's due, then writes that week's predictions.

For gameweek N this writes:

    fpts_model/game_logs/<season>/gw<NN-1>.csv    gameweek N-1's stat lines, added to the training history
    fpts_model/models/gw<NN>.json        the model, trained on every game before gameweek N, including
                                         past seasons' games in game_logs/ (not in git)
    league_hub/predictions/gw<NN>.json   its prediction for every player with a fixture in gameweek N

Both are written once, as soon as gameweek N-1 has finished, and never change after that. Delete a
gameweek's predictions file to have it rebuilt. Gameweek 1 is due as soon as the season appears, and
trains on past seasons alone.

Run it from the soccer directory:

    python3 -m fpts_model.train              # train whatever is due
    python3 -m fpts_model.train --dry-run    # show what's due
    python3 -m fpts_model.train --rebuild-models    # recreate models missing from this machine
    python3 -m fpts_model.train --fetch-history     # fetch past seasons in HISTORICAL_LEAGUES not stored yet

Models are too big for GitHub, so they stay on the machine that trained them. The scheduled GitHub
Action (.github/workflows/fpts-model.yml) runs the first form daily and commits only the game logs and
predictions, so after pulling, --rebuild-models fills in the weeks it trained.
"""

import argparse
import base64
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fantrax_wrapper import FantasyScoringEngine, FantraxClient, available_prediction_weeks
from fantrax_wrapper.predictions import PREDICTIONS_DIR, load_week_predictions, predictions_path

from .data import (
    HISTORICAL_LEAGUES,
    LEAGUE_TZ,
    fetch_fixtures,
    fetch_history,
    fetch_player_pool,
    load_game_logs,
    load_history,
)
from .features import TARGET_STATS, build_features
from .model import CLEAN_SHEET_STAT, N_ESTIMATORS, FptsModel

SOCCER_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = Path(__file__).resolve().parent / "models"
LEAGUE_ID = os.getenv("FANTRAX_LEAGUE_ID", "iku2an1nmryzcfa2")

# Same allowance sync_data.py gives a gameweek to finish after its last kickoff
GAMEWEEK_END_AFTER_LAST_KICKOFF = timedelta(hours=8)


def model_path(week: int) -> Path:
    """Where a gameweek's model is stored."""
    return MODELS_DIR / f"gw{week:02d}.json"


def weeks_due(gw_dates: Dict[int, Dict[str, date]], fixtures: pd.DataFrame, now: datetime) -> List[int]:
    """Gameweeks with no predictions yet whose previous gameweek has finished."""
    existing = set(available_prediction_weeks())
    due = []
    for week in sorted(gw_dates):
        if week in existing:
            continue
        if week == min(gw_dates):
            due.append(week)
            continue
        previous = fixtures.loc[fixtures["week"] == week - 1, "kickoff"]
        if previous.empty:
            finished = datetime.combine(gw_dates[week - 1]["end"] + timedelta(days=1), datetime.min.time(), LEAGUE_TZ)
        else:
            finished = previous.max() + GAMEWEEK_END_AFTER_LAST_KICKOFF
        if finished <= now:
            due.append(week)
    return due


def remove_old_seasons(season: int) -> None:
    """Clears last season's predictions and models, whose gameweek numbers would otherwise look already
    done. Game logs stay: they're stored by season and keep training later models."""
    weeks = available_prediction_weeks()
    if not weeks or load_week_predictions(weeks[0]).get("season") == season:
        return
    for directory in (PREDICTIONS_DIR, MODELS_DIR):
        for path in directory.glob("gw*"):
            path.unlink()


def fixture_rows(game_logs: pd.DataFrame, pool: pd.DataFrame, fixtures: pd.DataFrame, week: int) -> pd.DataFrame:
    """A blank game log row for each player's fixtures in a gameweek, including players yet to appear.

    Players are placed at the last club they played for before the gameweek, or their current club.
    """
    clubs = game_logs.sort_values("Date").groupby("player_id")["Team"].last()
    players = pool[["player_id", "position"]].assign(
        Team=pool["player_id"].map(clubs).fillna(pool["club"])
    )
    this_week = fixtures[fixtures["week"] == week]
    rows = players.merge(this_week, left_on="Team", right_on="club")
    return pd.DataFrame({
        "player_id": rows["player_id"],
        "position": rows["position"],
        "Date": pd.to_datetime(rows["kickoff"].map(lambda kickoff: kickoff.date())),
        "Team": rows["Team"],
        "Opp": rows["opp"],
    })


def prediction_entries(predictions: pd.DataFrame, pool: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """Per-player entries for a gameweek's predictions file."""
    rules = FantasyScoringEngine().rules
    players = pool.set_index("player_id")
    entries = {}
    for row in predictions.to_dict("records"):
        player = players.loc[row["player_id"]]
        rates = {stat: row[stat] for stat in TARGET_STATS if stat != CLEAN_SHEET_STAT}
        clean_sheet_chance = row[CLEAN_SHEET_STAT]
        scoring = {
            position: {
                "per_min": round(sum(rules[position].get(stat.upper(), 0) * rate for stat, rate in rates.items()), 5),
                "clean_sheet": round(rules[position].get("CS", 0) * clean_sheet_chance, 3),
            }
            for position in {row["position"], *player["positions"].split(",")}
        }
        entries[row["player_id"]] = {
            "name": player["name"],
            "club": row["team"],
            "position": row["position"],
            "positions": player["positions"],
            "fixtures": row["fixtures"],
            "basis": row["basis"],
            "scoring": scoring,
            "clean_sheet_chance": round(clean_sheet_chance, 3),
            "per_minute": {stat: round(rate, 5) for stat, rate in rates.items() if round(rate, 5)},
        }
    return entries


def past_season_features(before_season: int) -> pd.DataFrame:
    """Feature rows for every past season.

    Raises:
        RuntimeError: A season's files are missing. Training would otherwise quietly lose its history.
    """
    if before_season - 1 not in HISTORICAL_LEAGUES:
        raise RuntimeError(f"Add the {before_season - 1} league to HISTORICAL_LEAGUES, then run --fetch-history")
    frames = []
    for season in sorted(HISTORICAL_LEAGUES):
        if season >= before_season:
            continue
        logs, gw_dates = load_history(season)
        if logs.empty:
            raise RuntimeError(f"No stored game logs for {season}. Run python3 -m fpts_model.train --fetch-history")
        frames.append(build_features(logs, gw_dates))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def week_features(
    week: int,
    game_logs: pd.DataFrame,
    pool: pd.DataFrame,
    fixtures: pd.DataFrame,
    gw_dates: Dict[int, Dict[str, date]],
    past: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """This season's games before a gameweek, and the feature table for them, its fixtures and past seasons."""
    history = game_logs[game_logs["Date"].dt.date < gw_dates[week]["start"]]
    upcoming = fixture_rows(history, pool, fixtures, week)
    features = build_features(pd.concat([history, upcoming], ignore_index=True), gw_dates)
    return history, pd.concat([past, features], ignore_index=True) if past is not None and not past.empty else features


def rebuild_model(
    week: int,
    game_logs: pd.DataFrame,
    pool: pd.DataFrame,
    fixtures: pd.DataFrame,
    gw_dates: Dict[int, Dict[str, date]],
    past: Optional[pd.DataFrame] = None,
    n_estimators: int = N_ESTIMATORS,
) -> None:
    """Recreates a gameweek's model file from its stored predictions' metadata. Predictions don't change."""
    _, features = week_features(week, game_logs, pool, fixtures, gw_dates, past)
    document = load_week_predictions(week)
    metadata = {key: document[key] for key in ("season", "trained_through_week", "training_games", "games_this_season", "generated_at")}
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    FptsModel.train(features, week, n_estimators=n_estimators).save(model_path(week), metadata)
    print(f"GW {week}: rebuilt model", flush=True)


def train_week(
    week: int,
    game_logs: pd.DataFrame,
    pool: pd.DataFrame,
    fixtures: pd.DataFrame,
    gw_dates: Dict[int, Dict[str, date]],
    season: int,
    past: Optional[pd.DataFrame] = None,
    n_estimators: int = N_ESTIMATORS,
) -> None:
    """Trains, stores and predicts one gameweek, using only games from before it started."""
    history, features = week_features(week, game_logs, pool, fixtures, gw_dates, past)

    model = FptsModel.train(features, week, n_estimators=n_estimators)
    metadata = {
        "season": season,
        "trained_through_week": week - 1,
        "training_games": int(((features["season"] < season) | (features["matchweek"] < week)).sum()),
        "games_this_season": len(history),
        "generated_at": datetime.now(LEAGUE_TZ).isoformat(timespec="seconds"),
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save(model_path(week), metadata)

    # Predicting from the saved file keeps the stored model and the published numbers the same thing
    predictions = FptsModel.load(model_path(week)).predict(features)
    document = {**metadata, "week": week, "players": prediction_entries(predictions, pool)}
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    predictions_path(week).write_text(json.dumps(document, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    size_mb = model_path(week).stat().st_size / 1_000_000
    print(f"GW {week}: trained on {metadata['training_games']} games, predicted {len(document['players'])} players, model {size_mb:.0f} MB", flush=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Train and store the fantasy points model for every gameweek that's due.")
    parser.add_argument("--dry-run", action="store_true", help="show what's due and stop")
    parser.add_argument("--rebuild-models", action="store_true", help="recreate models missing from this machine and stop")
    parser.add_argument("--fetch-history", action="store_true", help="fetch past seasons not stored yet and stop")
    args = parser.parse_args(argv)

    if os.getenv("FANTRAX_COOKIE_B64") and not os.getenv("FANTRAX_COOKIE_PATH"):
        cookie_file = Path(tempfile.gettempdir()) / "fantraxloggedin.cookie"
        cookie_file.write_bytes(base64.b64decode("".join(os.environ["FANTRAX_COOKIE_B64"].split()), validate=True))
        os.environ["FANTRAX_COOKIE_PATH"] = str(cookie_file)
    cookie_path = os.getenv("FANTRAX_COOKIE_PATH") or str(SOCCER_DIR.parent / "fantraxloggedin.cookie")

    if args.fetch_history:
        for past_season, league_id in sorted(HISTORICAL_LEAGUES.items(), reverse=True):
            fetch_history(FantraxClient(league_id=league_id, cookie_path=cookie_path), past_season)
        return 0

    client = FantraxClient(league_id=LEAGUE_ID, cookie_path=cookie_path)
    gw_dates = client.get_gameweek_dates()
    if not gw_dates:
        raise RuntimeError("Fantrax returned no gameweek dates. The login cookie has probably expired.")
    season = gw_dates[min(gw_dates)]["start"].year
    fixtures = fetch_fixtures(gw_dates)

    if not args.dry_run:
        remove_old_seasons(season)
    if args.rebuild_models:
        missing = [week for week in available_prediction_weeks() if not model_path(week).exists()]
        print(f"Models to rebuild: {missing or 'none'}", flush=True)
        if missing:
            pool = fetch_player_pool(client)
            game_logs = load_game_logs(client, season, list(range(1, max(missing))), gw_dates, fixtures)
            past = past_season_features(season)
            for week in missing:
                rebuild_model(week, game_logs, pool, fixtures, gw_dates, past)
        return 0

    due = weeks_due(gw_dates, fixtures, datetime.now(LEAGUE_TZ))
    print(f"Gameweeks due: {due or 'none'}", flush=True)
    if args.dry_run or not due:
        return 0

    pool = fetch_player_pool(client)
    game_logs = load_game_logs(client, season, list(range(1, max(due))), gw_dates, fixtures)
    past = past_season_features(season)
    print(f"Past-season games to train on: {len(past)}", flush=True)
    for week in due:
        train_week(week, game_logs, pool, fixtures, gw_dates, season, past)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
