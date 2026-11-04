"""
Unit tests for the fantasy points model: features, leak checks, storage, and weekly training.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fantrax_wrapper import FantasyScoringEngine, with_predictions
from fantrax_wrapper import predictions as predictions_module
from fpts_model import TARGET_STATS, FptsModel, build_features, feature_columns
from fpts_model import data as data_module
from fpts_model import train as train_module
from fpts_model.data import LEAGUE_TZ

SEASON_START = date(2026, 8, 21)
UPCOMING_WEEK = 5
CLUBS = ["AAA", "BBB", "CCC", "DDD"]
POSITIONS = ["G", "D", "M", "F"]
GW_DATES = {
    week: {"start": SEASON_START + timedelta(weeks=week - 1), "end": SEASON_START + timedelta(weeks=week, days=-1)}
    for week in range(1, 7)
}


def week_day(week: int) -> pd.Timestamp:
    return pd.Timestamp(GW_DATES[week]["start"])


def make_pool() -> pd.DataFrame:
    rows = [
        {"player_id": f"{club}{pos}", "name": f"{club} {pos}", "position": pos, "positions": pos, "club": club}
        for club in CLUBS for pos in POSITIONS
    ]
    rows.append({"player_id": "NEW", "name": "New Signing", "position": "M", "positions": "M,F", "club": "AAA"})
    return pd.DataFrame(rows)


def pairing(week: int):
    """AAA and CCC always win at home; the away sides rotate."""
    return [("AAA", "BBB"), ("CCC", "DDD")] if week % 2 else [("AAA", "DDD"), ("CCC", "BBB")]


def make_game_logs(through_week: int = UPCOMING_WEEK - 1) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for week in range(1, through_week + 1):
        for home, away in pairing(week):
            for club, opp, score in ((home, away, "W 2-1"), (away, f"@{home}", "L 1-2")):
                for pos in POSITIONS:
                    row = {"player_id": f"{club}{pos}", "position": pos, "Date": week_day(week), "Team": club, "Opp": opp, "Score": score, "Min": "90"}
                    row.update({stat.upper(): str(rng.poisson(1.5)) for stat in TARGET_STATS})
                    if pos == "G":
                        row["GA"], row["GAO"] = "1", None
                    rows.append(row)
    return pd.DataFrame(rows)


def make_fixtures() -> pd.DataFrame:
    rows = []
    for week in range(1, 7):
        kickoff = datetime.combine(GW_DATES[week]["start"], datetime.min.time(), LEAGUE_TZ) + timedelta(hours=15)
        for home, away in pairing(week):
            rows.append({"week": week, "kickoff": kickoff, "club": home, "opp": away})
            rows.append({"week": week, "kickoff": kickoff, "club": away, "opp": f"@{home}"})
    return pd.DataFrame(rows)


def features_for_week(week: int, logs: pd.DataFrame = None) -> pd.DataFrame:
    logs = make_game_logs() if logs is None else logs
    history = logs[logs["Date"].dt.date < GW_DATES[week]["start"]]
    upcoming = train_module.fixture_rows(history, make_pool(), make_fixtures(), week)
    return build_features(pd.concat([history, upcoming], ignore_index=True), GW_DATES)


class TestBuildFeatures(unittest.TestCase):
    def test_uses_fantrax_gameweeks_and_venue(self):
        features = build_features(make_game_logs(), GW_DATES)
        self.assertEqual(sorted(features["matchweek"].unique()), [1, 2, 3, 4])
        self.assertTrue((features.loc[features["team"] == "AAA", "is_away"] == 0).all())
        self.assertTrue((features.loc[features["team"] == "BBB", "is_away"] == 1).all())

    def test_goalkeeper_goals_conceded_come_from_ga(self):
        features = build_features(make_game_logs(), GW_DATES)
        self.assertTrue((features.loc[features["player_id"] == "AAAG", "gao"] == 1).all())

    def test_rates_use_previous_games_only(self):
        logs = make_game_logs()
        features = build_features(logs, GW_DATES)
        rows = features[features["player_id"] == "AAAF"].set_index("matchweek")
        goals = logs[logs["player_id"] == "AAAF"].sort_values("Date")["G"].astype(int).tolist()
        self.assertEqual(rows.loc[1, "g_per_90_gameweek"], 0)
        self.assertAlmostEqual(rows.loc[3, "g_per_90_gameweek"], round(goals[1] / 90, 3) * 90)
        self.assertAlmostEqual(rows.loc[3, "g_per_90_season"], round(sum(goals[:2]) / 180, 3) * 90)

    def test_standings_use_earlier_gameweeks_only(self):
        features = build_features(make_game_logs(), GW_DATES)
        week_two = features[features["matchweek"] == 2]
        self.assertEqual(week_two.loc[week_two["team"] == "AAA", "team_week_standing"].iloc[0], 1)
        self.assertEqual(week_two.loc[week_two["team"] == "BBB", "team_week_standing"].iloc[0], 3)
        self.assertEqual(week_two.loc[week_two["team"] == "AAA", "team_week_standing_opp"].iloc[0], 4)

    def test_first_meeting_with_an_opponent_has_no_positional_average(self):
        features = build_features(make_game_logs(), GW_DATES)
        week_one = features[features["matchweek"] == 1]
        self.assertTrue((week_one["positional_avg_kp_per_90_season"] == 0).all())

    def test_every_feature_ignores_its_own_and_later_gameweeks(self):
        """The leak check: change all results from week 3 on, and features through week 3 must not move."""
        logs = make_game_logs()
        changed = logs.copy()
        from_week_three = changed["Date"] >= week_day(3)
        changed.loc[from_week_three, [stat.upper() for stat in TARGET_STATS]] = "9"
        changed.loc[from_week_three, "Min"] = "45"
        changed.loc[from_week_three, "Score"] = "L 0-5"

        columns = sorted({col for stat in TARGET_STATS for col in feature_columns(stat)})
        before = build_features(logs, GW_DATES).query("matchweek <= 3")[columns].reset_index(drop=True)
        after = build_features(changed, GW_DATES).query("matchweek <= 3")[columns].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)

    def test_training_rows_match_regardless_of_cutoff(self):
        """A week 3 row looks the same in week 4's feature table as in week 5's."""
        columns = sorted({col for stat in TARGET_STATS for col in feature_columns(stat)})
        key = ["matchweek", "player_id"]
        early = features_for_week(4).query("matchweek == 3").sort_values(key)[columns].reset_index(drop=True)
        late = features_for_week(5).query("matchweek == 3").sort_values(key)[columns].reset_index(drop=True)
        pd.testing.assert_frame_equal(early, late)

    def test_second_fixture_in_a_week_keeps_the_players_form(self):
        logs = make_game_logs()
        first = pd.DataFrame({"player_id": ["AAAF"], "position": ["F"], "Date": [week_day(5)], "Team": ["AAA"], "Opp": ["BBB"]})
        second = first.assign(Date=week_day(5) + pd.Timedelta(days=3), Opp="@CCC")
        features = build_features(pd.concat([logs, first, second], ignore_index=True), GW_DATES)
        rows = features[(features["player_id"] == "AAAF") & (features["matchweek"] == 5)]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows["kp_per_90_season"].nunique(), 1)
        self.assertEqual(rows["kp_per_90_gameweek"].nunique(), 1)

    def test_rejects_multiple_seasons(self):
        logs = make_game_logs()
        logs["season"] = [2024] * 6 + [2025] * (len(logs) - 6)
        with self.assertRaises(ValueError):
            build_features(logs, GW_DATES)

    def test_rejects_games_outside_every_gameweek(self):
        logs = make_game_logs()
        logs.loc[0, "Date"] = pd.Timestamp("2030-01-01")
        with self.assertRaises(ValueError):
            build_features(logs, GW_DATES)


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = features_for_week(UPCOMING_WEEK)
        cls.model = FptsModel.train(cls.features, UPCOMING_WEEK, n_estimators=5)

    def test_trains_one_forest_per_stat(self):
        self.assertEqual(set(self.model.forests), set(TARGET_STATS))

    def test_predicts_every_player_with_a_fixture(self):
        predictions = self.model.predict(self.features)
        self.assertEqual(set(predictions["player_id"]), set(make_pool()["player_id"]))
        self.assertTrue(predictions[TARGET_STATS + ["fpts_pred"]].notna().all().all())

    def test_points_follow_the_scoring_rules(self):
        engine = FantasyScoringEngine()
        predictions = self.model.predict(self.features)
        for _, row in predictions.iterrows():
            self.assertEqual(row["fpts_pred"], engine.calculate_fantasy_score(row[TARGET_STATS].to_dict(), row["position"]))
        self.assertGreater(predictions["fpts_pred"].nunique(), 1)

    def test_training_excludes_the_predicted_week(self):
        predicted_week_stats = self.features[self.features["matchweek"] == UPCOMING_WEEK]
        self.assertFalse(predicted_week_stats["played"].any())
        self.assertEqual(self.features.loc[self.features["played"], "matchweek"].max(), UPCOMING_WEEK - 1)

    def test_saved_model_keeps_every_tree_and_predicts_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gw05.json"
            self.model.save(path, {"season": 2026})
            document = json.loads(path.read_text())
            loaded = FptsModel.load(path)
        self.assertEqual(document["week"], UPCOMING_WEEK)
        self.assertEqual(len(document["forests"]["kp"]), 5)
        pd.testing.assert_frame_equal(self.model.predict(self.features), loaded.predict(self.features))

    def test_json_forest_matches_scikit_learn(self):
        from sklearn.ensemble import RandomForestRegressor
        from fpts_model.model import JsonForest

        encoded = self.model._encode(self.features)
        train = encoded[encoded["played"]]
        columns = feature_columns("kp")
        forest = RandomForestRegressor(n_estimators=10, random_state=42).fit(train[columns], train["kp"])
        np.testing.assert_array_equal(JsonForest.from_sklearn(forest).predict(encoded[columns]), forest.predict(encoded[columns]))

    def test_missing_gameweek_raises(self):
        with self.assertRaises(ValueError):
            FptsModel(UPCOMING_WEEK + 1, {}, {}).predict(self.features)

    def test_nothing_to_train_on_raises(self):
        logs = make_game_logs(through_week=1)
        with self.assertRaises(ValueError):
            FptsModel.train(build_features(logs, GW_DATES), 1, n_estimators=2)


class FakeClient:
    """Returns one player per club position, as FantraxClient.get_player_stats does for a date range."""

    def __init__(self, players_per_club=12):
        self.players_per_club = players_per_club
        self.calls = 0

    def get_player_stats(self, start_date=None, end_date=None, limit=50):
        self.calls += 1
        players = [
            {"id": f"{club}{n}", "name": f"{club} {n}", "scored_as": "M", "club": club, "games_played": 1, "minutes": 90,
             "stats": {"G": 1, "KP": 2, "GAO": 1, "SV": 3}}
            for club in CLUBS for n in range(self.players_per_club)
        ]
        players.append({"id": "bench", "name": "Unused", "scored_as": "M", "club": "AAA", "games_played": 0, "minutes": 0, "stats": {}})
        return players


class TestGameLogData(unittest.TestCase):
    def fixtures(self, score="W 2-1"):
        return make_fixtures().assign(score=score)

    def test_week_stat_lines_match_clean_game_logs(self):
        logs = data_module.fetch_week_game_logs(FakeClient(), 3, GW_DATES, self.fixtures())
        self.assertEqual(len(logs), 48)
        self.assertNotIn("bench", set(logs["player_id"]))
        row = logs[logs["player_id"] == "BBB0"].iloc[0]
        self.assertEqual((row["Team"], row["Opp"], row["Score"], row["Min"]), ("BBB", "@AAA", "W 2-1", 90))
        self.assertEqual((row["g"], row["kp"], row["gao"], row["sv"]), (1, 2, 1, 3))
        build_features(logs, GW_DATES)

    def test_incomplete_listing_raises(self):
        with self.assertRaisesRegex(RuntimeError, "too few players"):
            data_module.fetch_week_game_logs(FakeClient(players_per_club=3), 3, GW_DATES, self.fixtures())

    def test_unfinished_gameweek_raises(self):
        with self.assertRaisesRegex(RuntimeError, "no final score"):
            data_module.fetch_week_game_logs(FakeClient(), 3, GW_DATES, self.fixtures(score=None))

    def test_finished_weeks_are_only_fetched_once(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp, patch.object(data_module, "GAME_LOGS_DIR", Path(tmp)), \
                patch.object(data_module, "PAUSE_BETWEEN_WEEKS_SECONDS", 0):
            first = data_module.load_game_logs(client, [1, 2], GW_DATES, self.fixtures())
            second = data_module.load_game_logs(client, [1, 2], GW_DATES, self.fixtures())
        self.assertEqual(client.calls, 2)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first["player_id"].dtype.kind in "OU" or str(first["player_id"].dtype) == "str", True)

    def test_results_read_from_the_clubs_side(self):
        self.assertEqual(data_module._result(4, 0), "W 4-0")
        self.assertEqual(data_module._result(0, 4), "L 0-4")
        self.assertEqual(data_module._result(1, 1), "T 1-1")
        self.assertIsNone(data_module._result(None, None))


class TestWeeklyTraining(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.predictions_dir = Path(tmp.name) / "predictions"
        self.models_dir = Path(tmp.name) / "models"
        self.predictions_dir.mkdir()
        for patcher in (
            patch.object(predictions_module, "PREDICTIONS_DIR", self.predictions_dir),
            patch.object(train_module, "PREDICTIONS_DIR", self.predictions_dir),
            patch.object(train_module, "MODELS_DIR", self.models_dir),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_predictions(self, week: int, season: int = 2026) -> None:
        predictions_module.predictions_path(week).write_text(json.dumps({"season": season, "players": {}}))

    def test_week_one_is_never_due(self):
        now = datetime.combine(GW_DATES[1]["start"], datetime.min.time(), LEAGUE_TZ)
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), now), [])

    def test_next_week_is_due_once_the_previous_one_finishes(self):
        last_kickoff = make_fixtures().query("week == 2")["kickoff"].max()
        before = last_kickoff + timedelta(hours=7)
        after = last_kickoff + timedelta(hours=9)
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), before), [2])
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), after), [2, 3])

    def test_existing_weeks_are_not_redone(self):
        self.write_predictions(2)
        last_kickoff = make_fixtures().query("week == 2")["kickoff"].max()
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), last_kickoff + timedelta(hours=9)), [3])

    def test_old_seasons_are_cleared(self):
        self.write_predictions(2, season=2025)
        self.write_predictions(3, season=2025)
        with patch.object(train_module, "GAME_LOGS_DIR", self.predictions_dir.parent / "logs"):
            train_module.GAME_LOGS_DIR.mkdir()
            (train_module.GAME_LOGS_DIR / "gw01.csv").write_text("old")
            train_module.remove_old_seasons(2026)
            self.assertEqual(list(train_module.GAME_LOGS_DIR.iterdir()), [])
        self.assertEqual(predictions_module.available_prediction_weeks(), [])

    def test_current_season_is_kept(self):
        self.write_predictions(2, season=2026)
        train_module.remove_old_seasons(2026)
        self.assertEqual(predictions_module.available_prediction_weeks(), [2])

    def test_players_stay_at_the_club_they_last_played_for(self):
        logs = make_game_logs(through_week=2)
        pool = make_pool()
        pool.loc[pool["player_id"] == "AAAF", "club"] = "BBB"  # transferred after the week being predicted
        rows = train_module.fixture_rows(logs, pool, make_fixtures(), 3)
        self.assertEqual(rows.loc[rows["player_id"] == "AAAF", "Team"].item(), "AAA")
        self.assertEqual(rows.loc[rows["player_id"] == "NEW", "Team"].item(), "AAA")

    def test_train_week_writes_model_and_predictions_from_earlier_games_only(self):
        logs = make_game_logs(through_week=UPCOMING_WEEK)
        train_module.train_week(3, logs, make_pool(), make_fixtures(), GW_DATES, 2026, n_estimators=3)

        model = json.loads(train_module.model_path(3).read_text())
        document = predictions_module.load_week_predictions(3)
        self.assertEqual(model["trained_through_week"], 2)
        self.assertEqual(document["training_games"], 32)
        self.assertEqual(set(document["players"]), set(make_pool()["player_id"]))
        self.assertEqual(document["players"]["AAAF"]["fixtures"], ["BBB"])
        self.assertEqual(set(document["players"]["NEW"]["by_position"]), {"M", "F"})

        # Later results must not change what week 3's model predicts
        changed = logs.copy()
        changed.loc[changed["Date"] >= week_day(3), "G"] = "9"
        train_module.train_week(3, changed, make_pool(), make_fixtures(), GW_DATES, 2026, n_estimators=3)
        self.assertEqual(predictions_module.load_week_predictions(3)["players"]["AAAF"]["fpts"], document["players"]["AAAF"]["fpts"])

    def test_rebuilt_model_matches_the_original_and_leaves_predictions_alone(self):
        logs = make_game_logs(through_week=UPCOMING_WEEK)
        train_module.train_week(3, logs, make_pool(), make_fixtures(), GW_DATES, 2026, n_estimators=3)
        original = train_module.model_path(3).read_bytes()
        predictions = predictions_module.predictions_path(3).read_bytes()

        train_module.model_path(3).unlink()
        train_module.rebuild_model(3, logs, make_pool(), make_fixtures(), GW_DATES, n_estimators=3)

        self.assertEqual(train_module.model_path(3).read_bytes(), original)
        self.assertEqual(predictions_module.predictions_path(3).read_bytes(), predictions)

    def test_lineups_get_predictions_at_their_slot(self):
        predictions_module.predictions_path(4).write_text(json.dumps({"season": 2026, "players": {
            "a": {"fpts": 5.0}, "b": {"fpts": 6.0, "by_position": {"M": 6.0, "F": 7.5}},
        }}))
        lineup = {
            "starters": [{"id": "a", "slot": "D"}, {"id": "b", "slot": "F"}, {"id": "c", "slot": "M"}],
            "bench": [], "injured_reserve": [],
        }
        result = with_predictions(lineup, 4)
        self.assertEqual([p["predicted"] for p in result["starters"]], [5.0, 7.5, None])
        self.assertNotIn("predicted", lineup["starters"][0])
        self.assertIs(with_predictions(lineup, 9), lineup)


if __name__ == "__main__":
    unittest.main()
