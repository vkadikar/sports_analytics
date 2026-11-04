"""
Unit tests for the fantasy points model's features and train/predict flow.
"""

import os
import sys
import unittest

import pandas as pd
import pytest

pytest.importorskip("sklearn")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fantrax_wrapper.scoring import FantasyScoringEngine
from fpts_model import TARGET_STATS, build_features, feature_columns, predict_gameweek, train_stat_models

UPCOMING_WEEK = 5
PLAYERS = [
    ("a1", "AAA", "G"), ("a2", "AAA", "D"), ("a3", "AAA", "F"),
    ("b1", "BBB", "G"), ("b2", "BBB", "M"), ("b3", "BBB", "F"),
]


def make_game_logs() -> pd.DataFrame:
    """AAA hosts BBB every week and wins 2-1, with the last week still to be played."""
    rows = []
    for week in range(1, UPCOMING_WEEK + 1):
        played = week < UPCOMING_WEEK
        for player_id, team, position in PLAYERS:
            home = team == "AAA"
            row = {
                "player_id": player_id,
                "position": position,
                "Date": pd.Timestamp("2025-08-16") + pd.Timedelta(weeks=week - 1),
                "Team": team,
                "Opp": "BBB" if home else "@AAA",
                "Score": ("W 2-1" if home else "L 1-2") if played else "L 0-0",
                "Min": "90" if played else None,
                "GA": ("1" if home else "2") if played and position == "G" else None,
            }
            for stat in TARGET_STATS:
                row[stat.upper()] = str(week) if played else None
            row["GAO"] = None if position == "G" else row["GAO"]
            rows.append(row)
    return pd.DataFrame(rows)


class TestBuildFeatures(unittest.TestCase):
    def test_assigns_matchweek_and_venue(self):
        features = build_features(make_game_logs())
        self.assertEqual(sorted(features["matchweek"].unique()), [1, 2, 3, 4, 5])
        self.assertTrue((features.loc[features["team"] == "BBB", "is_away"] == 1).all())
        self.assertTrue((features.loc[features["team"] == "AAA", "is_away"] == 0).all())
        self.assertEqual(set(features["opp"]), {"AAA", "BBB"})

    def test_goalkeeper_goals_conceded_come_from_ga(self):
        features = build_features(make_game_logs())
        keeper = features[(features["player_id"] == "b1") & (features["matchweek"] == 1)]
        self.assertEqual(keeper["gao"].item(), 2)

    def test_rates_use_previous_games_only(self):
        features = build_features(make_game_logs())
        rows = features[features["player_id"] == "a3"].set_index("matchweek")
        self.assertEqual(rows.loc[1, "g_per_90_gameweek"], 0)  # no previous game
        self.assertAlmostEqual(rows.loc[3, "g_per_90_gameweek"], round(2 / 90, 3) * 90)
        self.assertAlmostEqual(rows.loc[3, "g_per_90_season"], round(3 / 180, 3) * 90)

    def test_standings_use_previous_results_only(self):
        features = build_features(make_game_logs())
        week_one = features[features["matchweek"] == 1]
        week_two = features[features["matchweek"] == 2]
        # Both sides are level before a ball is kicked, then AAA leads
        self.assertEqual(set(week_one["team_week_standing"]), {1, 2})
        self.assertTrue((week_two.loc[week_two["team"] == "AAA", "team_week_standing"] == 1).all())
        self.assertTrue((week_two.loc[week_two["team"] == "AAA", "team_week_standing_opp"] == 2).all())

    def test_result_of_a_week_does_not_change_its_own_features(self):
        logs = make_game_logs()
        changed = logs.copy()
        in_week_three = changed["Date"] == pd.Timestamp("2025-08-16") + pd.Timedelta(weeks=2)
        changed.loc[in_week_three, "G"] = "9"

        columns = [col for col in feature_columns("kp") if col not in ("player_id", "team", "opp", "position")]
        columns += ["g_per_90_gameweek", "g_per_90_season"]
        before = build_features(logs).query("matchweek == 3")[columns].reset_index(drop=True)
        after = build_features(changed).query("matchweek == 3")[columns].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)

    def test_rejects_multiple_seasons(self):
        logs = make_game_logs()
        logs["season"] = [2024] * 6 + [2025] * (len(logs) - 6)
        with self.assertRaises(ValueError):
            build_features(logs)


class TestFeatureColumns(unittest.TestCase):
    def test_rolling_stat_has_rate_features(self):
        self.assertIn("kp_per_90_season", feature_columns("kp"))
        self.assertIn("positional_avg_kp_per_90_gameweek", feature_columns("kp"))
        self.assertEqual(len(feature_columns("kp")), 13)

    def test_context_only_stat_has_context_features(self):
        self.assertEqual(len(feature_columns("yc")), 7)


class TestTrainAndPredict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = build_features(make_game_logs())
        cls.models = train_stat_models(cls.features, UPCOMING_WEEK, n_estimators=5)

    def test_trains_one_model_per_stat(self):
        self.assertEqual(set(self.models), set(TARGET_STATS))

    def test_predicts_upcoming_week_for_every_player(self):
        predictions = predict_gameweek(self.models, self.features, UPCOMING_WEEK)
        self.assertEqual(set(predictions["player_id"]), {player[0] for player in PLAYERS})
        self.assertTrue(predictions[TARGET_STATS + ["fpts_pred"]].notna().all().all())

    def test_fpts_follow_position_scoring_rules(self):
        predictions = predict_gameweek(self.models, self.features, UPCOMING_WEEK)
        engine = FantasyScoringEngine()
        for _, row in predictions.iterrows():
            expected = engine.calculate_fantasy_score(row[TARGET_STATS].to_dict(), row["position"])
            self.assertEqual(row["fpts_pred"], expected)
        self.assertGreater(predictions["fpts_pred"].nunique(), 1)

    def test_missing_gameweek_raises(self):
        with self.assertRaises(ValueError):
            predict_gameweek(self.models, self.features, UPCOMING_WEEK + 1)

    def test_nothing_to_train_on_raises(self):
        with self.assertRaises(ValueError):
            train_stat_models(self.features, 1)


if __name__ == "__main__":
    unittest.main()
