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

from fantrax_wrapper import FantasyScoringEngine, player_prediction, points_at_minutes, with_predictions
from fantrax_wrapper import predictions as predictions_module
from fpts_model import TARGET_STATS, FptsModel, build_features, feature_columns
from sklearn.ensemble import RandomForestRegressor
from fpts_model import data as data_module
from fpts_model import evaluate as evaluate_module
from fpts_model import model as model_module
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
        self.assertEqual(rows.loc[1, "g_per_min_gameweek"], 0)
        self.assertAlmostEqual(rows.loc[3, "g_per_min_gameweek"], goals[1] / 90)
        self.assertAlmostEqual(rows.loc[3, "g_per_min_season"], sum(goals[:2]) / 180)

    def test_standings_use_earlier_gameweeks_only(self):
        features = build_features(make_game_logs(), GW_DATES)
        week_two = features[features["matchweek"] == 2]
        self.assertEqual(week_two.loc[week_two["team"] == "AAA", "team_week_standing"].iloc[0], 1)
        self.assertEqual(week_two.loc[week_two["team"] == "BBB", "team_week_standing"].iloc[0], 3)
        self.assertEqual(week_two.loc[week_two["team"] == "AAA", "team_week_standing_opp"].iloc[0], 4)

    def test_first_meeting_with_an_opponent_has_no_positional_average(self):
        features = build_features(make_game_logs(), GW_DATES)
        week_one = features[features["matchweek"] == 1]
        self.assertTrue((week_one["positional_avg_kp_per_min_season"] == 0).all())

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
        self.assertEqual(rows["kp_per_min_season"].nunique(), 1)
        self.assertEqual(rows["kp_per_min_gameweek"].nunique(), 1)

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
        self.assertTrue(predictions[TARGET_STATS].notna().all().all())

    def test_predictions_are_rates_not_game_totals(self):
        """Every game in the fixture is 90 minutes, so rates average the game totals over 90."""
        predictions = self.model.predict(self.features)
        self.assertLess(predictions["kp"].max(), make_game_logs()["KP"].astype(int).max() / 90 + 1e-9)
        self.assertGreater(predictions["kp"].max(), 0)

    def fit_calls(self, logs):
        """The rows, targets and weights each forest was fitted with."""
        calls = {}

        class Recording(RandomForestRegressor):
            def fit(self, X, y, sample_weight=None):
                calls[len(calls)] = {"X": X, "y": y, "weight": sample_weight}
                return super().fit(X, y, sample_weight=sample_weight)

        with patch.object(model_module, "RandomForestRegressor", Recording):
            FptsModel.train(build_features(logs, GW_DATES), UPCOMING_WEEK, n_estimators=2)
        return {stat: calls[i] for i, stat in enumerate(TARGET_STATS)}

    def test_stat_forests_learn_per_minute_weighted_by_minutes(self):
        logs = make_game_logs()
        logs.loc[logs["Team"] == "AAA", "Min"] = "30"
        logs["KP"] = "3"
        call = self.fit_calls(logs)["kp"]
        self.assertEqual(set(call["y"].round(6)), {0.1, round(3 / 90, 6)})
        self.assertEqual(call["weight"].max(), 90)

    def test_clean_sheet_forest_learns_a_per_game_chance_from_60_minute_games(self):
        logs = make_game_logs()
        logs["CS"] = "1"
        logs.loc[logs["Team"] == "AAA", "Min"] = "59"
        logs.loc[logs["Team"] == "BBB", "Min"] = "60"
        call = self.fit_calls(logs)["cs"]
        self.assertTrue((call["weight"] <= 1).all())  # recency only, not minutes
        self.assertTrue((call["y"] == 1).all())
        self.assertEqual(len(call["y"]), (logs["Min"].astype(int) >= 60).sum())

    def test_every_leaf_must_hold_a_minimum_of_evidence(self):
        class Recording(RandomForestRegressor):
            seen = []

            def fit(self, X, y, sample_weight=None):
                Recording.seen.append((self.min_weight_fraction_leaf, self.min_samples_leaf, sample_weight))
                return super().fit(X, y, sample_weight=sample_weight)

        logs = make_game_logs()
        with patch.object(model_module, "RandomForestRegressor", Recording):
            FptsModel.train(build_features(logs, GW_DATES), UPCOMING_WEEK, n_estimators=2)
        fraction, _, weight = Recording.seen[TARGET_STATS.index("kp")]
        self.assertAlmostEqual(fraction, min(model_module.MIN_LEAF_MINUTES / weight.sum(), 0.5))
        fraction, _, weight = Recording.seen[TARGET_STATS.index("cs")]
        self.assertAlmostEqual(fraction, min(model_module.MIN_LEAF_CLEAN_SHEET_GAMES / weight.sum(), 0.5))

    def test_older_games_count_for_less(self):
        dates = pd.to_datetime(pd.Series(["2026-10-01", "2025-10-01", "2024-10-01"]))
        with patch.object(model_module, "RECENCY_HALF_LIFE_DAYS", 365):
            weights = model_module.recency_weights(dates).tolist()
        self.assertEqual(weights[0], 1)
        self.assertAlmostEqual(weights[1], 0.5)
        self.assertAlmostEqual(weights[2], 0.25, places=2)

    def test_player_without_minutes_gets_their_positions_record_against_the_opponent(self):
        logs = make_game_logs()
        logs["KP"], logs["CS"] = "0", "0"
        # Midfielders have 9 key passes per game against BBB, and clean sheets in half of those games
        against_bbb = (logs["Opp"].str.replace("@", "") == "BBB") & (logs["position"] == "M")
        logs.loc[against_bbb, "KP"] = "9"
        logs.loc[logs.index[against_bbb][::2], "CS"] = "1"
        rows = train_module.fixture_rows(logs, make_pool(), make_fixtures(), UPCOMING_WEEK)
        self.assertEqual(rows.loc[rows["player_id"] == "NEW", "Opp"].item(), "BBB")
        features = build_features(pd.concat([logs, rows], ignore_index=True), GW_DATES)
        predictions = FptsModel.train(features, UPCOMING_WEEK, n_estimators=3).predict(features).set_index("player_id")

        self.assertEqual(predictions.loc["NEW", "basis"], "position_vs_opponent")
        self.assertAlmostEqual(predictions.loc["NEW", "kp"], 0.1)
        self.assertAlmostEqual(predictions.loc["NEW", "cs"], logs.loc[against_bbb, "CS"].astype(int).mean())
        self.assertEqual(predictions.loc["AAAM", "basis"], "player")

    def test_thin_opponent_record_falls_back_to_the_position_overall(self):
        logs = make_game_logs()
        logs["KP"] = "9"
        logs.loc[logs["Opp"].str.replace("@", "") == "BBB", "Min"] = "1"  # under the minimum minutes
        rows = train_module.fixture_rows(logs, make_pool(), make_fixtures(), UPCOMING_WEEK)
        features = build_features(pd.concat([logs, rows], ignore_index=True), GW_DATES)
        predictions = FptsModel.train(features, UPCOMING_WEEK, n_estimators=3).predict(features).set_index("player_id")
        self.assertEqual(predictions.loc["NEW", "basis"], "position")
        history = features[features["played"] & (features["position"] == "M")]
        self.assertAlmostEqual(predictions.loc["NEW", "kp"], history["kp"].sum() / history["minutes"].sum())

    def test_short_appearances_do_not_inflate_a_predicted_rate(self):
        """One big cameo among 90-minute games barely moves the rate, because it carries little weight."""
        logs = make_game_logs()
        logs["KP"] = "9"
        cameo = logs.index[(logs["player_id"] == "AAAF") & (logs["Date"] == week_day(1))]
        logs.loc[cameo, ["Min", "KP"]] = ["1", "5"]
        features = build_features(pd.concat([logs, train_module.fixture_rows(logs, make_pool(), make_fixtures(), UPCOMING_WEEK)], ignore_index=True), GW_DATES)
        predictions = FptsModel.train(features, UPCOMING_WEEK, n_estimators=50).predict(features).set_index("player_id")
        self.assertLess(predictions.loc["AAAF", "kp"], 0.5)

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
        from fpts_model.model import JsonForest

        encoded = self.model._encode(self.features)
        train = encoded[encoded["played"]]
        columns = feature_columns("kp")
        forest = RandomForestRegressor(n_estimators=10, random_state=42).fit(train[columns], train["kp"])
        np.testing.assert_array_equal(JsonForest.from_sklearn(forest).predict(encoded[columns]), forest.predict(encoded[columns]))

    def test_past_seasons_are_trained_on_with_less_weight_but_never_predicted(self):
        past_dates = {
            week: {key: value - timedelta(days=364) for key, value in dates.items()} for week, dates in GW_DATES.items()
        }
        past_logs = make_game_logs().assign(Date=lambda logs: logs["Date"] - pd.Timedelta(days=364))
        past = build_features(past_logs, past_dates)
        self.assertEqual(past["season"].unique().tolist(), [2025])
        features = pd.concat([past, self.features], ignore_index=True)

        calls = []

        class Recording(RandomForestRegressor):
            def fit(self, X, y, sample_weight=None):
                calls.append((len(y), sample_weight))
                return super().fit(X, y, sample_weight=sample_weight)

        with patch.object(model_module, "RandomForestRegressor", Recording):
            model = FptsModel.train(features, UPCOMING_WEEK, n_estimators=2)
        rows, weights = calls[TARGET_STATS.index("kp")]
        self.assertEqual(rows, len(past) + self.features["played"].sum())
        self.assertLess(weights.iloc[:len(past)].mean(), weights.iloc[len(past):].mean() * 0.75)

        predictions = model.predict(features)
        self.assertEqual(set(predictions["player_id"]), set(make_pool()["player_id"]))
        self.assertEqual(predictions["fixtures"].map(len).max(), 1)

    def test_no_minutes_this_season_ignores_past_seasons_and_uses_this_seasons_opponent_record(self):
        past_dates = {
            week: {key: value - timedelta(days=364) for key, value in dates.items()} for week, dates in GW_DATES.items()
        }
        logs = make_game_logs()
        logs["KP"] = "0"
        last_year = make_game_logs().assign(Date=lambda frame: frame["Date"] - pd.Timedelta(days=364), KP="9")
        last_year.loc[last_year.index[:4], "player_id"] = "NEW"  # played last season, not this one
        past = build_features(last_year, past_dates)
        features = features_for_week(UPCOMING_WEEK, logs)
        features = pd.concat([past, features], ignore_index=True)
        predictions = FptsModel.train(features, UPCOMING_WEEK, n_estimators=2).predict(features).set_index("player_id")
        self.assertEqual(predictions.loc["NEW", "basis"], "position_vs_opponent")
        self.assertEqual(predictions.loc["NEW", "kp"], 0)

    def test_form_and_standings_reset_each_season(self):
        features = build_features(make_game_logs(), GW_DATES)
        self.assertTrue((features.loc[features["matchweek"] == 1, "kp_per_min_season"] == 0).all())

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

    def test_transferred_players_use_their_latest_club_unless_dropped(self):
        client = FakeClient()
        moved = {"id": "moved", "name": "Moved", "scored_as": "M", "club": "CCC/BBB", "games_played": 1, "minutes": 90, "stats": {}}
        original = client.get_player_stats
        client.get_player_stats = lambda **kwargs: original(**kwargs) + [moved]
        logs = data_module.fetch_week_game_logs(client, 3, GW_DATES, self.fixtures())
        self.assertEqual(logs.loc[logs["player_id"] == "moved", "Team"].item(), "BBB")
        dropped = data_module.fetch_week_game_logs(client, 3, GW_DATES, self.fixtures(), drop_transfers=True)
        self.assertNotIn("moved", set(dropped["player_id"]))

    def test_transferred_players_count_towards_a_clubs_completeness(self):
        client = FakeClient(players_per_club=10)
        original = client.get_player_stats
        extra = [{"id": f"m{club}", "name": "Moved", "scored_as": "M", "club": f"ZZZ/{club}", "games_played": 1, "minutes": 90, "stats": {}} for club in CLUBS]
        client.get_player_stats = lambda **kwargs: original(**kwargs) + extra
        data_module.fetch_week_game_logs(client, 3, GW_DATES, self.fixtures(), drop_transfers=True)

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
            first = data_module.load_game_logs(client, 2026, [1, 2], GW_DATES, self.fixtures())
            second = data_module.load_game_logs(client, 2026, [1, 2], GW_DATES, self.fixtures())
        self.assertEqual(client.calls, 2)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first["player_id"].dtype.kind in "OU" or str(first["player_id"].dtype) == "str", True)

    def test_flipped_results_read_from_the_other_clubs_side(self):
        self.assertEqual(data_module._flip_result("W 3-1"), "L 1-3")
        self.assertEqual(data_module._flip_result("L 0-2"), "W 2-0")
        self.assertEqual(data_module._flip_result("T 1-1"), "T 1-1")

    def test_historical_fixtures_use_few_game_logs_and_cover_both_clubs(self):
        class Client:
            calls = []

            def get_player_game_log(self, player_id, year):
                self.calls.append(player_id)
                return pd.DataFrame([
                    {"Team": "AAA", "Opp": "BBB", "Score": "W 2-1", "Date_dt": pd.Timestamp(GW_DATES[1]["start"])},
                    {"Team": "AAA", "Opp": "@CCC", "Score": "T 0-0", "Date_dt": pd.Timestamp(GW_DATES[2]["start"])},
                    {"Team": "AAA", "Opp": "DDD", "Score": "L 0-1", "Date_dt": pd.Timestamp("2030-01-01")},
                ])

        players = [
            {"id": "a1", "club": "AAA", "minutes": 900},
            {"id": "moved", "club": "AAA/BBB", "minutes": 3000},
        ]
        with patch.object(data_module, "PAUSE_BETWEEN_PROFILES_SECONDS", 0), patch.object(data_module, "GAMES_PER_CLUB", 3):
            fixtures = data_module.fetch_historical_fixtures(Client(), 2025, GW_DATES, players)
        self.assertEqual(Client.calls, ["a1"])
        rows = fixtures.set_index(["week", "club"])
        self.assertEqual((rows.loc[(1, "AAA"), "opp"], rows.loc[(1, "AAA"), "score"]), ("BBB", "W 2-1"))
        self.assertEqual((rows.loc[(1, "BBB"), "opp"], rows.loc[(1, "BBB"), "score"]), ("@AAA", "L 1-2"))
        self.assertEqual((rows.loc[(2, "CCC"), "opp"], rows.loc[(2, "CCC"), "score"]), ("AAA", "T 0-0"))
        self.assertEqual(set(fixtures["week"]), {1, 2})  # the game outside every gameweek is dropped

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

    def test_week_one_is_due_as_soon_as_the_season_appears(self):
        now = datetime.combine(GW_DATES[1]["start"] - timedelta(days=30), datetime.min.time(), LEAGUE_TZ)
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), now), [1])

    def test_next_week_is_due_once_the_previous_one_finishes(self):
        last_kickoff = make_fixtures().query("week == 2")["kickoff"].max()
        before = last_kickoff + timedelta(hours=7)
        after = last_kickoff + timedelta(hours=9)
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), before), [1, 2])
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), after), [1, 2, 3])

    def test_existing_weeks_are_not_redone(self):
        self.write_predictions(1)
        self.write_predictions(2)
        last_kickoff = make_fixtures().query("week == 2")["kickoff"].max()
        self.assertEqual(train_module.weeks_due(GW_DATES, make_fixtures(), last_kickoff + timedelta(hours=9)), [3])

    def test_old_seasons_are_cleared(self):
        self.write_predictions(2, season=2025)
        self.write_predictions(3, season=2025)
        train_module.remove_old_seasons(2026)
        self.assertEqual(predictions_module.available_prediction_weeks(), [])

    def test_current_season_is_kept(self):
        self.write_predictions(2, season=2026)
        train_module.remove_old_seasons(2026)
        self.assertEqual(predictions_module.available_prediction_weeks(), [2])

    def test_a_missing_last_season_stops_training(self):
        with self.assertRaisesRegex(RuntimeError, "HISTORICAL_LEAGUES"):
            train_module.past_season_features(2030)

    def test_week_one_trains_on_past_seasons_and_uses_last_seasons_position_record(self):
        past_dates = {
            week: {key: value - timedelta(days=364) for key, value in dates.items()} for week, dates in GW_DATES.items()
        }
        last_year = make_game_logs().assign(Date=lambda frame: frame["Date"] - pd.Timedelta(days=364), KP="0")
        faced_bbb = (last_year["Opp"].str.replace("@", "") == "BBB") & (last_year["position"] == "M")
        last_year.loc[faced_bbb, "KP"] = "9"
        past = build_features(last_year, past_dates)
        with tempfile.TemporaryDirectory() as tmp, patch.object(data_module, "GAME_LOGS_DIR", Path(tmp)):
            no_games = data_module.load_game_logs(None, 2026, [], GW_DATES, make_fixtures())

        train_module.train_week(1, no_games, make_pool(), make_fixtures(), GW_DATES, 2026, past, n_estimators=2)

        document = predictions_module.load_week_predictions(1)
        self.assertEqual(document["trained_through_week"], 0)
        self.assertEqual(document["games_this_season"], 0)
        self.assertEqual(document["training_games"], len(past))
        self.assertEqual(set(document["players"]), set(make_pool()["player_id"]))
        # GW1 pairs AAA with BBB, so AAA's midfielder faces BBB; CCC's faces DDD, and DDD's has no KP
        self.assertEqual(document["players"]["AAAM"]["basis"], "position_vs_opponent")
        self.assertAlmostEqual(document["players"]["AAAM"]["per_minute"]["kp"], 0.1)
        self.assertNotIn("kp", document["players"]["CCCM"]["per_minute"])

    def test_missing_history_stops_training(self):
        with patch.object(train_module, "load_history", return_value=(pd.DataFrame(), {})):
            with self.assertRaisesRegex(RuntimeError, "fetch-history"):
                train_module.past_season_features(2026)

    def test_only_earlier_seasons_are_history(self):
        calls = []
        with patch.object(train_module, "load_history", side_effect=lambda season: calls.append(season) or (make_game_logs(), GW_DATES)):
            train_module.past_season_features(2024)
        self.assertEqual(calls, [2023])

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
        self.assertEqual(set(document["players"]["NEW"]["scoring"]), {"M", "F"})

        # Later results must not change what week 3's model predicts
        changed = logs.copy()
        changed.loc[changed["Date"] >= week_day(3), "G"] = "9"
        train_module.train_week(3, changed, make_pool(), make_fixtures(), GW_DATES, 2026, n_estimators=3)
        self.assertEqual(predictions_module.load_week_predictions(3)["players"]["AAAF"]["scoring"], document["players"]["AAAF"]["scoring"])

    def test_rebuilt_model_matches_the_original_and_leaves_predictions_alone(self):
        logs = make_game_logs(through_week=UPCOMING_WEEK)
        train_module.train_week(3, logs, make_pool(), make_fixtures(), GW_DATES, 2026, n_estimators=3)
        original = train_module.model_path(3).read_bytes()
        predictions = predictions_module.predictions_path(3).read_bytes()

        train_module.model_path(3).unlink()
        train_module.rebuild_model(3, logs, make_pool(), make_fixtures(), GW_DATES, n_estimators=3)

        self.assertEqual(train_module.model_path(3).read_bytes(), original)
        self.assertEqual(predictions_module.predictions_path(3).read_bytes(), predictions)

    def test_entries_score_rates_and_clean_sheets_by_position(self):
        rates = {stat: 0.0 for stat in TARGET_STATS}
        rates.update(g=0.01, cs=0.5)
        predictions = pd.DataFrame([{"player_id": "NEW", "team": "AAA", "position": "M", "fixtures": ["BBB"], "basis": "player", **rates}])
        entry = train_module.prediction_entries(predictions, make_pool())["NEW"]
        rules = FantasyScoringEngine().rules
        self.assertEqual(entry["scoring"]["M"], {"per_min": round(rules["M"]["G"] * 0.01, 5), "clean_sheet": rules["M"]["CS"] * 0.5})
        self.assertEqual(entry["scoring"]["F"], {"per_min": round(rules["F"]["G"] * 0.01, 5), "clean_sheet": 0})

    def test_points_scale_with_minutes_and_clean_sheets_start_at_60(self):
        prediction = {"per_min": 0.1, "clean_sheet": 2.0, "games": 1}
        self.assertEqual(points_at_minutes(prediction, 0), 0)
        self.assertEqual(points_at_minutes(prediction, 45), 4.5)
        self.assertEqual(points_at_minutes(prediction, 59), 5.9)
        self.assertEqual(points_at_minutes(prediction, 60), 8.0)
        self.assertEqual(points_at_minutes(prediction, 90), 11.0)
        self.assertEqual(points_at_minutes({**prediction, "games": 2}, 90), 22.0)

    def test_lineups_get_predictions_at_their_slot(self):
        scoring = {"M": {"per_min": 0.1, "clean_sheet": 1.0}, "F": {"per_min": 0.2, "clean_sheet": 0}}
        predictions_module.predictions_path(4).write_text(json.dumps({"season": 2026, "players": {
            "a": {"position": "M", "fixtures": ["X"], "basis": "player", "scoring": {"M": scoring["M"]}},
            "b": {"position": "M", "fixtures": ["X", "Y"], "basis": "position_vs_opponent", "scoring": scoring},
        }}))
        lineup = {
            "starters": [{"id": "a", "slot": "M"}, {"id": "b", "slot": "F"}, {"id": "c", "slot": "M"}],
            "bench": [{"id": "b", "slot": ""}], "injured_reserve": [],
        }
        result = with_predictions(lineup, 4)
        self.assertEqual(result["starters"][0]["prediction"], {"per_min": 0.1, "clean_sheet": 1.0, "games": 1, "basis": "player"})
        self.assertEqual(result["starters"][1]["prediction"], {"per_min": 0.2, "clean_sheet": 0, "games": 2, "basis": "position_vs_opponent"})
        self.assertIsNone(result["starters"][2]["prediction"])
        self.assertEqual(result["bench"][0]["prediction"]["per_min"], 0.1)
        self.assertNotIn("prediction", lineup["starters"][0])
        self.assertIs(with_predictions(lineup, 9), lineup)

    def test_errors_use_actual_minutes_and_skip_players_who_did_not_play(self):
        predictions_module.predictions_path(2).write_text(json.dumps({"season": 2026, "players": {
            "a": {"position": "D", "fixtures": ["X"], "basis": "player", "scoring": {"D": {"per_min": 0.1, "clean_sheet": 3.0}}},
            "b": {"position": "D", "fixtures": ["X"], "basis": "player", "scoring": {"D": {"per_min": 0.1, "clean_sheet": 3.0}}},
            "new": {"position": "D", "fixtures": ["X"], "basis": "position_vs_opponent", "scoring": {"D": {"per_min": 0.1, "clean_sheet": 3.0}}},
        }}))
        games = pd.DataFrame([
            {"player_id": "a", "week": 1, "position": "D", "Min": 90, "actual": 9.0},
            {"player_id": "b", "week": 1, "position": "D", "Min": 90, "actual": 9.0},
            {"player_id": "a", "week": 2, "position": "D", "Min": 30, "actual": 2.0},
            {"player_id": "b", "week": 2, "position": "D", "Min": 0, "actual": 0.0},
            {"player_id": "new", "week": 2, "position": "D", "Min": 90, "actual": 5.0},
        ])
        all_errors = evaluate_module.prediction_errors(games, [2])
        self.assertEqual(len(all_errors), 2)  # "b" didn't play
        self.assertEqual(all_errors.loc[~all_errors["has_history"], "model"].item(), 12.0)  # "new": 90 minutes
        errors = all_errors[all_errors["has_history"]]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors["model"].item(), 3.0)  # 30 minutes: no clean sheet
        self.assertEqual(errors["baseline"].item(), 3.0)
        self.assertEqual(errors["actual"].item(), 2.0)


if __name__ == "__main__":
    unittest.main()
