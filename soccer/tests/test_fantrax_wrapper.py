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
    calculate_optimal_standings,
    compare_standings_vs_optimal,
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

    def test_calculate_manager_efficiency(self):
        df = pd.DataFrame([
            {"week": 1, "team": "Team A", "score": 80.0, "opponent_score": 70.0, "max_points_for": 95.0},
            {"week": 1, "team": "Team B", "score": 70.0, "opponent_score": 80.0, "max_points_for": 85.0},
            {"week": 2, "team": "Team A", "score": 0.0, "opponent_score": 0.0, "max_points_for": 15.0},
            {"week": 2, "team": "Team B", "score": 0.0, "opponent_score": 0.0, "max_points_for": 15.0},
        ])
        efficiency = calculate_manager_efficiency(df, only_completed=True)
        self.assertEqual(len(efficiency), 2)
        # Should only evaluate Week 1 (15 missed points), ignoring unplayed Week 2
        self.assertEqual(efficiency.loc["Team A", "total_missed_points"], 15.0)
        self.assertEqual(efficiency.loc["Team A", "avg_actual_score"], 80.0)

    def test_calculate_median_standings(self):
        df = pd.DataFrame([
            {"week": 1, "team": "Team A", "score": 45.0, "opponent_score": 30.0},
            {"week": 1, "team": "Team B", "score": 30.0, "opponent_score": 45.0},
            {"week": 1, "team": "Team C", "score": 60.0, "opponent_score": 20.0},
            {"week": 1, "team": "Team D", "score": 20.0, "opponent_score": 60.0},
            {"week": 2, "team": "Team A", "score": 0.0, "opponent_score": 0.0},
            {"week": 2, "team": "Team B", "score": 0.0, "opponent_score": 0.0},
        ])
        standings = calculate_median_standings(df, only_completed=True)
        self.assertIn("wins", standings.columns)
        self.assertEqual(len(standings), 4)
        # Verify unplayed week did not add draws
        self.assertEqual(standings["draws"].sum(), 0)

    def test_calculate_optimal_standings(self):
        df = pd.DataFrame([
            {"week": 1, "matchupId": 0, "team": "Team A", "score": 80.0, "opponent_score": 70.0, "max_points_for": 85.0},
            {"week": 1, "matchupId": 0, "team": "Team B", "score": 70.0, "opponent_score": 80.0, "max_points_for": 90.0},
            {"week": 1, "matchupId": 1, "team": "Team C", "score": 60.0, "opponent_score": 50.0, "max_points_for": 65.0},
            {"week": 1, "matchupId": 1, "team": "Team D", "score": 50.0, "opponent_score": 60.0, "max_points_for": 55.0},
        ])
        # Team B actually lost (70 vs 80), but optimally won (90 vs 85)
        opt_standings = calculate_optimal_standings(df)
        self.assertEqual(len(opt_standings), 4)
        self.assertEqual(opt_standings.loc["Team B", "wins"], 1)
        self.assertEqual(opt_standings.loc["Team A", "losses"], 1)

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

    @patch("fantrax_wrapper.client.FantraxRPCClient.send_rpc_request")
    def test_get_gameweek_dates_mock(self, mock_rpc):
        mock_rpc.return_value = {
            "responses": [
                {
                    "data": {
                        "tableList": [
                            {"caption": "Gameweek 1", "subCaption": "(Fri Aug 21, 2026 - Thu Aug 27, 2026)", "rows": []},
                            {"caption": "Gameweek 2", "subCaption": "", "rows": []},
                            {"caption": "Gameweek 3", "subCaption": "(Fri May 28, 2027 - Sun May 30, 2027)", "rows": []},
                        ]
                    }
                }
            ]
        }

        client = FantraxClient(league_id="test_league", cookie_path=None)
        dates = client.get_gameweek_dates()

        self.assertEqual(sorted(dates), [1, 3])
        self.assertEqual(dates[1]["start"], datetime(2026, 8, 21).date())
        self.assertEqual(dates[1]["end"], datetime(2026, 8, 27).date())
        self.assertEqual(dates[3]["end"], datetime(2027, 5, 30).date())

    @patch("fantrax_wrapper.client.FantraxRPCClient.send_rpc_request")
    def test_get_lineup_mock(self, mock_rpc):
        def roster(points):
            header = {"cells": [{"shortName": n} for n in ("Opp", "FPts", "FP/G", "GP", "Min")]}
            def row(sid, name, pos, status, slot, pts):
                return {"statusId": status, "posId": slot,
                        "scorer": {"scorerId": sid, "name": name, "posShortNames": pos, "teamShortName": "ARS"},
                        "cells": [{"content": "ARS 1<br/>@NOT 0 F"}, {"content": pts}, {"content": ""}, {"content": "1"}, {"content": "90"}]}
            rows = [
                row("p1", "Keeper", "G", "1", "704", points[0]),
                row("p2", "Defender", "D,F", "1", "703", points[1]),
                row("p3", "Benched", "M", "2", "702", points[2]),
                {"statusId": "1", "posId": "701", "scorer": {}, "cells": []},  # empty slot
                {"statusId": "y", "scorer": {}, "cells": [{"content": ""}, {"content": "99"}]},  # totals row
            ]
            return {"responses": [{"data": {"tables": [{"header": header, "rows": rows}]}}]}

        # First call: "Fantasy Team" view (what counted); second: each player's own points.
        mock_rpc.side_effect = [roster(["6", "-3.5", "0"]), roster(["6", "5", "8"])]

        client = FantraxClient(league_id="test_league", cookie_path=None)
        lineup = client.get_lineup("team1", 7)

        self.assertEqual([p["name"] for p in lineup["starters"]], ["Keeper", "Defender"])
        self.assertEqual(lineup["starters"][1]["points"], -3.5)
        self.assertEqual(lineup["starters"][1]["slot"], "D")
        self.assertEqual(lineup["total"], 2.5)
        self.assertEqual(lineup["bench"][0]["points"], 8.0)
        self.assertEqual(lineup["starters"][0]["game"], "ARS 1 @NOT 0 F")
        self.assertEqual(lineup["starters"][0]["minutes"], 90)


if __name__ == "__main__":
    unittest.main()
