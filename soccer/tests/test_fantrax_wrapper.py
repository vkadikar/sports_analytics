"""
Unit tests for fantrax_wrapper module.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pandas as pd

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fantrax_wrapper import (
    FantraxClient,
    FantasyScoringEngine,
    add_season_year,
    parse_opponent,
    compute_optimal_lineup_score,
    calculate_manager_efficiency,
    calculate_median_standings,
    evaluate_waiver_candidates,
    normalize_per_90_stats,
    compute_positional_opponent_averages,
)


class TestUtils(unittest.TestCase):
    def test_add_season_year_august(self):
        dt = add_season_year("Aug 17", 2024)
        self.assertEqual(dt, datetime(2024, 8, 17))

    def test_add_season_year_january(self):
        dt = add_season_year("Jan 12", 2024)
        self.assertEqual(dt, datetime(2025, 1, 12))

    def test_parse_opponent_home(self):
        opp, is_home = parse_opponent("ARS")
        self.assertEqual(opp, "ARS")
        self.assertTrue(is_home)

    def test_parse_opponent_away(self):
        opp, is_home = parse_opponent("@BRE")
        self.assertEqual(opp, "BRE")
        self.assertFalse(is_home)


class TestScoringEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FantasyScoringEngine()

    def test_midfielder_scoring(self):
        # Goal = 9, Key Pass = 2, Shots on Target = 2
        stats = {"G": 1, "KP": 2, "SOT": 1}
        score = self.engine.calculate_fantasy_score(stats, "M")
        # 9*1 + 2*2 + 2*1 = 15.0
        self.assertEqual(score, 15.0)

    def test_goalkeeper_scoring(self):
        # Clean Sheet = 8, Saves = 2 (x2 = 4), Goals Against = -2
        stats = {"CS": 1, "SV": 2, "GAO": 1}
        score = self.engine.calculate_fantasy_score(stats, "G")
        # 8*1 + 2*2 + (-2)*1 = 10.0
        self.assertEqual(score, 10.0)

    def test_adjusted_fantasy_score_excludes_goals_and_assists(self):
        stats = {"G": 1, "AT": 1, "KP": 2}
        score = self.engine.calculate_adjusted_fantasy_score(stats, "M")
        # Only KP (2*2 = 4.0) included
        self.assertEqual(score, 4.0)


class TestAnalytics(unittest.TestCase):
    def test_compute_optimal_lineup_score(self):
        g_scores = [12.0, 5.0]
        d_scores = [15.0, 10.0, 8.0, 6.0, 4.0, 2.0]
        m_scores = [18.0, 14.0, 11.0, 7.0, 3.0]
        f_scores = [20.0, 16.0, 9.0]

        # Top picks:
        # G: 12.0
        # Mandatory D (3): 15, 10, 8
        # Mandatory M (2): 18, 14
        # Mandatory F (1): 20
        # Rem: D(6, 4, 2), M(11, 7, 3), F(16, 9)
        # Greedily add 4: 16 (F), 11 (M), 9 (F - max 3 F reached!), 7 (M)
        # Total = 12 + (15+10+8) + (18+14+11+7) + (20+16+9) = 12 + 33 + 50 + 45 = 140.0
        score = compute_optimal_lineup_score(g_scores, d_scores, m_scores, f_scores)
        self.assertGreater(score, 100.0)

    def test_calculate_median_standings(self):
        df = pd.DataFrame([
            {"week": 1, "team": "Team A", "score": 45.0, "opponent_score": 30.0},
            {"week": 1, "team": "Team B", "score": 30.0, "opponent_score": 45.0},
            {"week": 1, "team": "Team C", "score": 60.0, "opponent_score": 20.0},
            {"week": 1, "team": "Team D", "score": 20.0, "opponent_score": 60.0},
        ])
        standings = calculate_median_standings(df)
        self.assertIn("wins", standings.columns)
        self.assertEqual(len(standings), 4)

    def test_evaluate_waiver_candidates(self):
        df_stats = pd.DataFrame([
            {
                "player_name": "Player 1",
                "position": "M",
                "last_week_minutes": 90,
                "games_played": 10,
                "season_fpts": 100.0,
            },
            {
                "player_name": "Rostered Player",
                "position": "F",
                "last_week_minutes": 90,
                "games_played": 10,
                "season_fpts": 150.0,
            },
        ])
        rostered = ["Rostered Player"]
        waivers = evaluate_waiver_candidates(df_stats, rostered_player_names=rostered, current_week=1)
        self.assertEqual(len(waivers), 1)
        self.assertEqual(waivers.iloc[0]["player_name"], "Player 1")


class TestFantraxClient(unittest.TestCase):
    @patch("fantrax_wrapper.client.FantraxRPCClient.send_rpc_request")
    def test_get_matchups_mock(self, mock_rpc):
        mock_rpc.return_value = {
            "responses": [
                {
                    "data": {
                        "tableList": [
                            {
                                "rows": [
                                    {
                                        "cells": [
                                            {"content": "Team Alpha", "teamId": "t1"},
                                            {"content": "55.5"},
                                            {"content": "Team Beta", "teamId": "t2"},
                                            {"content": "42.0"},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }

        client = FantraxClient(league_id="test_league", cookie_path=None)
        matchups_df = client.get_matchups(through_week=1, as_dataframe=True)

        self.assertEqual(len(matchups_df), 2)
        self.assertIn("team", matchups_df.columns)
        self.assertEqual(matchups_df.iloc[0]["team"], "Team Alpha")
        self.assertEqual(matchups_df.iloc[0]["score"], 55.5)

    @patch("fantrax_wrapper.client.FantraxRPCClient.send_rpc_request")
    def test_get_draft_rankings_mock(self, mock_rpc):
        mock_rpc.return_value = {
            "responses": [
                {
                    "data": {
                        "fullStats": [
                            {
                                "scorer": {
                                    "scorerId": "01abc",
                                    "name": "Sample Player",
                                    "shortName": "S. Player",
                                    "teamShortName": "ARS",
                                    "teamName": "Arsenal",
                                    "posShortNames": "<b>M</b>",
                                },
                                "adp": 1.5,
                                "score": 250.0,
                                "scorePerGame": 8.5,
                                "percentDrafted": 95.0,
                            }
                        ]
                    }
                }
            ]
        }

        client = FantraxClient(league_id="test_league", cookie_path=None)
        ranks_df = client.get_draft_rankings(as_dataframe=True)

        self.assertEqual(len(ranks_df), 1)
        self.assertEqual(ranks_df.iloc[0]["name"], "Sample Player")
        self.assertEqual(ranks_df.iloc[0]["position"], "M")
        self.assertEqual(ranks_df.iloc[0]["adp"], 1.5)
        self.assertEqual(ranks_df.iloc[0]["projected_pts"], 250.0)


if __name__ == "__main__":
    unittest.main()
