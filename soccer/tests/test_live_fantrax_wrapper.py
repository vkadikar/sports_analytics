"""
Live integration test suite verifying authentication, cookie management,
and all Fantrax Client tools using credentials from soccer/config/.env.
"""

import os
import sys
import unittest
import pandas as pd

# Add soccer directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fantrax_wrapper import (
    FantraxClient,
    load_env_file,
    calculate_manager_efficiency,
    calculate_median_standings,
    evaluate_waiver_candidates,
)


class TestLiveFantraxWrapper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up live FantraxClient instance using soccer/config/.env settings."""
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
        cls.env_loaded = load_env_file(env_path)
        
        cls.username = os.getenv("FANTRAX_USERNAME")
        cls.password = os.getenv("FANTRAX_PASSWORD")
        cls.league_id = os.getenv("FANTRAX_LEAGUE_ID")

        if not cls.league_id:
            raise unittest.SkipTest("FANTRAX_LEAGUE_ID not set in soccer/config/.env")

        cls.cookie_file = "fantraxloggedin.cookie"
        cls.client = FantraxClient(
            league_id=cls.league_id,
            cookie_path=cls.cookie_file,
            env_file_path=env_path,
            auto_login=True,
        )

    def test_01_cookie_availability_and_authentication(self):
        """Test 1: Confirm availability of fantraxloggedin.cookie and active session authentication."""
        self.assertTrue(os.path.exists(self.cookie_file), f"Cookie file {self.cookie_file} should exist.")
        cookie_count = len(self.client.session_manager.session.cookies)
        self.assertGreater(cookie_count, 0, "Session should contain loaded Fantrax authentication cookies.")
        print(f"\n[PASS] Cookie verified: {self.cookie_file} contains {cookie_count} active cookies.")

    def test_02_get_matchups(self):
        """Test 2: Verify get_matchups live tool."""
        matchups_df = self.client.get_matchups(through_week=5, as_dataframe=True)
        self.assertIsInstance(matchups_df, pd.DataFrame)
        self.assertFalse(matchups_df.empty, "Matchups DataFrame should not be empty.")
        self.assertIn("score", matchups_df.columns)
        self.assertIn("opponent_score", matchups_df.columns)
        self.assertIn("result", matchups_df.columns)
        print(f"\n[PASS] get_matchups: Fetched {len(matchups_df)} matchup rows for weeks 1-5.")

    def test_03_get_league_table(self):
        """Test 3: Verify get_league_table live tool."""
        standings_df = self.client.get_league_table(through_week=5)
        self.assertIsInstance(standings_df, pd.DataFrame)
        self.assertFalse(standings_df.empty, "Standings DataFrame should not be empty.")
        self.assertIn("points", standings_df.columns)
        self.assertIn("record", standings_df.columns)
        print(f"\n[PASS] get_league_table: Standings calculated for {len(standings_df)} teams.")

    def test_04_get_team_roster(self):
        """Test 4: Verify get_team_roster live tool."""
        matchups_df = self.client.get_matchups(through_week=1, as_dataframe=True)
        self.assertFalse(matchups_df.empty)
        sample_team_id = matchups_df["team_id"].iloc[0]

        roster = self.client.get_team_roster(team_id=sample_team_id)
        self.assertIsNotNone(roster)
        self.assertEqual(roster.team_id, sample_team_id)
        self.assertGreater(len(roster.starters), 0, "Team roster should have starters.")
        print(f"\n[PASS] get_team_roster: Fetched {len(roster.starters)} starters and {len(roster.reserves)} reserves for Team {sample_team_id}.")

    def test_05_get_all_players(self):
        """Test 5: Verify get_all_players live tool."""
        players_df = self.client.get_all_players(as_dataframe=True)
        self.assertIsInstance(players_df, pd.DataFrame)
        self.assertFalse(players_df.empty, "Players DataFrame should not be empty.")
        self.assertIn("name", players_df.columns)
        self.assertIn("scorerId", players_df.columns)
        print(f"\n[PASS] get_all_players: Fetched {len(players_df)} total players from league database.")

    def test_06_get_player_game_log(self):
        """Test 6: Verify get_player_game_log live tool."""
        players_df = self.client.get_all_players(as_dataframe=True)
        self.assertFalse(players_df.empty)
        sample_player_id = players_df["scorerId"].iloc[0]
        sample_player_name = players_df["name"].iloc[0]

        game_log = self.client.get_player_game_log(player_id=sample_player_id, year=2025)
        self.assertIsInstance(game_log, pd.DataFrame)
        print(f"\n[PASS] get_player_game_log: Fetched {len(game_log)} game log entries for {sample_player_name}.")

    def test_07_get_player_news(self):
        """Test 7: Verify get_player_news live tool."""
        players_df = self.client.get_all_players(as_dataframe=True)
        self.assertFalse(players_df.empty)
        sample_player_id = players_df["scorerId"].iloc[0]

        news = self.client.get_player_news(player_id=sample_player_id)
        self.assertIsInstance(news, str)
        print(f"\n[PASS] get_player_news: Query returned news text (length {len(news)} chars).")

    def test_08_get_live_scoring(self):
        """Test 8: Verify get_live_scoring live tool."""
        live_df = self.client.get_live_scoring(period=1)
        self.assertIsInstance(live_df, pd.DataFrame)
        self.assertFalse(live_df.empty, "Live scoring DataFrame should not be empty.")
        self.assertIn("fantrax_projection", live_df.columns)
        print(f"\n[PASS] get_live_scoring: Fetched {len(live_df)} live projection rows for Week 1.")

    def test_09_manager_efficiency_analytics(self):
        """Test 9: Verify manager efficiency & median standings analytics."""
        matchups_df = self.client.get_matchups(through_week=5, as_dataframe=True)
        self.assertFalse(matchups_df.empty)

        matchups_df["max_points_for"] = matchups_df["score"] + 10.0
        efficiency_summary = calculate_manager_efficiency(matchups_df)
        self.assertFalse(efficiency_summary.empty)
        self.assertIn("avg_inefficiency", efficiency_summary.columns)

        median_standings = calculate_median_standings(matchups_df)
        self.assertFalse(median_standings.empty)
        print(f"\n[PASS] Manager Efficiency Analytics: Computed efficiency for {len(efficiency_summary)} teams.")

    def test_10_waiver_wire_evaluation(self):
        """Test 10: Verify waiver candidate evaluation analytics."""
        players_df = self.client.get_all_players(as_dataframe=True)
        self.assertFalse(players_df.empty)

        rostered = players_df["name"].iloc[:10].tolist()
        waivers = evaluate_waiver_candidates(players_df, rostered_player_names=rostered, current_week=5)
        self.assertIsInstance(waivers, pd.DataFrame)
        self.assertFalse(waivers.empty)
        print(f"\n[PASS] Waiver Analytics: Evaluated {len(waivers)} free agent candidates.")

    def test_11_get_draft_rankings(self):
        """Test 11: Verify get_draft_rankings live tool."""
        ranks_df = self.client.get_draft_rankings(league_id="iku2an1nmryzcfa2")
        self.assertIsInstance(ranks_df, pd.DataFrame)
        self.assertFalse(ranks_df.empty, "Draft rankings DataFrame should not be empty.")
        self.assertIn("rank", ranks_df.columns)
        self.assertIn("name", ranks_df.columns)
        self.assertIn("adp", ranks_df.columns)
        self.assertIn("projected_pts", ranks_df.columns)
        print(f"\n[PASS] get_draft_rankings: Fetched {len(ranks_df)} draft ranked players.")


if __name__ == "__main__":
    unittest.main()
