"""
Unit tests for how league_hub/sync_data.py fills in the cups from results.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "league_hub")))

import sync_data
from sync_data import (
    CL_GROUP_SEATS,
    CL_ROUNDS,
    CL_SCHEDULE_DEFS,
    CL_SLOTS,
    LINGINENI_ROUNDS,
    LINGINENI_SCHEDULE_DEFS,
    LINGINENI_SLOTS,
    bracket_rounds,
    build_cl_group_table,
    resolve_knockouts,
)

# Every club's fixed score, so the higher-scoring club always wins.
STRENGTH = {
    "Birds & Bees FC": 80, "MOO FC": 130, "seanbridges7": 91, "Estimated Profit": 54, "Wallalujah": 70,
    "Smip Estonian": 60, "Arnie-senal": 111, "WayneRooney10": 77, "FC Purulona": 92, "sduvuuru": 90,
    "Toadenham Frogspur": 104, "Traderjoe18": 75, "youngmoon": 87, "FC VAR": 100,
}


def season(through_gw, live_gw=None, scores=None):
    """gw_status and score_of for a season played through a gameweek."""
    def gw_status(gw):
        return "Final" if gw <= through_gw else "Live" if gw == live_gw else "Scheduled"

    def score_of(gw, team):
        if gw_status(gw) == "Scheduled" or team not in STRENGTH:
            return None
        return (scores or {}).get((gw, team), float(STRENGTH[team]))

    return gw_status, score_of


def resolve_cup(*args, **kwargs):
    gw_status, score_of = season(*args, **kwargs)
    return resolve_knockouts(LINGINENI_SCHEDULE_DEFS, LINGINENI_SLOTS, gw_status, score_of)


class TestLingineniCup(unittest.TestCase):
    def test_before_any_results_placeholders_remain(self):
        fixtures, ties = resolve_cup(8)
        self.assertEqual(fixtures[14][0]["homeTeam"], "Winner (Birds & Bees / MOO)")
        self.assertIsNone(ties["R1_M1"]["winner"])
        self.assertEqual(ties["R1_M1"]["status"], "Scheduled")

    def test_winner_advances_only_to_the_tie_it_feeds(self):
        fixtures, ties = resolve_cup(9)
        self.assertEqual(ties["R1_M1"]["winner"], "MOO FC")
        self.assertEqual(fixtures[14][0]["homeTeam"], "MOO FC")
        self.assertEqual(fixtures[14][3]["homeTeam"], "seanbridges7")
        self.assertEqual(fixtures[19][0]["awayTeam"], "Winner R2 Match 1")

    def test_live_gameweek_shows_scores_without_a_winner(self):
        _, ties = resolve_cup(8, live_gw=9)
        self.assertEqual(ties["R1_M1"]["status"], "Live")
        self.assertEqual(ties["R1_M1"]["awayScore"], 130)
        self.assertIsNone(ties["R1_M1"]["winner"])

    def test_bye_clubs_use_real_team_names_so_they_get_scores(self):
        _, ties = resolve_cup(19)
        self.assertEqual(ties["QF1"]["home"], "Toadenham Frogspur")
        self.assertEqual(ties["QF1"]["homeScore"], 104)

    def test_semi_final_is_on_aggregate_with_legs_swapped(self):
        # QF1 winner MOO FC v QF2 winner Arnie-senal. Arnie-senal lose leg 1 but win on aggregate.
        scores = {(24, "MOO FC"): 100.0, (24, "Arnie-senal"): 90.0,
                  (29, "Arnie-senal"): 120.0, (29, "MOO FC"): 80.0}
        fixtures, ties = resolve_cup(29, scores=scores)
        sf1 = ties["SF1"]
        self.assertEqual((sf1["home"], sf1["away"]), ("MOO FC", "Arnie-senal"))
        self.assertEqual((sf1["homeScore"], sf1["awayScore"]), (180.0, 210.0))
        self.assertEqual(sf1["winner"], "Arnie-senal")
        self.assertEqual(fixtures[29][0]["homeTeam"], "Arnie-senal")
        self.assertEqual(fixtures[34][0]["homeTeam"], "Arnie-senal")

    def test_semi_final_undecided_after_first_leg(self):
        fixtures, ties = resolve_cup(24)
        self.assertEqual(ties["SF1"]["status"], "Live")
        self.assertIsNone(ties["SF1"]["winner"])
        self.assertEqual(fixtures[34][0]["homeTeam"], "Winner Semi-Final 1")

    def test_champion_after_final(self):
        _, ties = resolve_cup(34)
        self.assertEqual(ties["FINAL"]["winner"], "MOO FC")

    def test_level_tie_waits_for_a_ruling(self):
        scores = {(9, "Birds & Bees FC"): 100.0, (9, "MOO FC"): 100.0}
        fixtures, ties = resolve_cup(9, scores=scores)
        self.assertEqual(ties["R1_M1"]["status"], "Final")
        self.assertIsNone(ties["R1_M1"]["winner"])
        self.assertTrue(ties["R1_M1"]["level"])
        self.assertEqual(fixtures[14][0]["homeTeam"], "Winner (Birds & Bees / MOO)")

        with patch.dict(sync_data.CUP_TIE_RULINGS, {"R1_M1": "Birds & Bees FC"}):
            fixtures, ties = resolve_cup(9, scores=scores)
        self.assertEqual(ties["R1_M1"]["winner"], "Birds & Bees FC")
        self.assertFalse(ties["R1_M1"]["level"])
        self.assertEqual(fixtures[14][0]["homeTeam"], "Birds & Bees FC")

    def test_tie_waiting_on_a_level_feeder_is_not_itself_level(self):
        scores = {(14, "Smip Estonian"): 88.0, (14, "Arnie-senal"): 88.0}
        _, ties = resolve_cup(19, scores=scores)
        self.assertTrue(ties["R2_M2"]["level"])
        self.assertEqual(ties["QF2"]["status"], "Final")
        self.assertFalse(ties["QF2"]["level"])

    def test_club_missing_from_matchups_is_not_knocked_out(self):
        def score_of(gw, team):
            return None if team == "MOO FC" else STRENGTH.get(team)
        _, ties = resolve_knockouts(LINGINENI_SCHEDULE_DEFS, LINGINENI_SLOTS, lambda gw: "Final", score_of)
        self.assertIsNone(ties["R1_M1"]["winner"])


class TestBracket(unittest.TestCase):
    def test_bracket_entries(self):
        _, ties = resolve_cup(14)
        rounds = bracket_rounds(LINGINENI_ROUNDS, ties)
        r2_m1 = rounds[1]["matches"][0]
        self.assertEqual(r2_m1["p1"], "Rahul Mohankumar (MOO FC)")
        self.assertEqual(r2_m1["winner"], "Rahul Mohankumar")
        qf1 = rounds[2]["matches"][0]
        self.assertEqual(qf1["p1"], "Ari Diddams (Bye)")
        self.assertEqual(qf1["p2"], "Rahul Mohankumar (MOO FC)")
        self.assertEqual(rounds[4]["matches"][0]["p1"], "Winner Semi-Final 1")


class TestChampionsLeague(unittest.TestCase):
    def test_group_table_counts_only_final_gameweeks(self):
        _, score_of = season(6)
        table = build_cl_group_table([6], score_of)
        self.assertEqual(len(table), 6)
        self.assertEqual(sum(r["w"] + r["d"] + r["l"] for r in table), 6)
        self.assertEqual([r["pos"] for r in table], [1, 2, 3, 4, 5, 6])

    def test_top_four_fill_semi_finals_and_champion_emerges(self):
        gws = list(range(1, 37))
        gw_status, score_of = season(36)
        table = build_cl_group_table(gws, score_of)
        seats = dict(zip(CL_GROUP_SEATS, (r["team"] for r in table)))
        fixtures, ties = resolve_knockouts(CL_SCHEDULE_DEFS, CL_SLOTS, gw_status, score_of, seats)
        self.assertEqual([r["team"] for r in table[:4]], ["Arnie-senal", "Toadenham Frogspur", "FC VAR", "youngmoon"])
        self.assertEqual((ties["CL_SF1"]["home"], ties["CL_SF1"]["away"]), ("Arnie-senal", "youngmoon"))
        self.assertEqual((ties["CL_SF2"]["home"], ties["CL_SF2"]["away"]), ("Toadenham Frogspur", "FC VAR"))
        self.assertEqual(fixtures[33][0]["homeTeam"], "youngmoon")
        self.assertEqual(ties["CL_FINAL"]["winner"], "Arnie-senal")
        self.assertEqual(bracket_rounds(CL_ROUNDS, ties)[1]["matches"][0]["winner"], "Arnav Jain")


if __name__ == "__main__":
    unittest.main()
