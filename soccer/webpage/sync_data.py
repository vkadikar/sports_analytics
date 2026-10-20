"""
Synchronize real Fantrax league data into data.js using the Fantrax API Wrapper.
"""

import os
import sys
import json
import pandas as pd
import numpy as np

# Ensure proper sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
SOCCER_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SOCCER_DIR not in sys.path:
    sys.path.insert(0, SOCCER_DIR)

from fantrax_wrapper import FantraxClient
from fantrax_wrapper.analytics import (
    calculate_manager_efficiency,
    calculate_median_standings,
    calculate_optimal_standings
)

TEAM_MANAGER_MAP = {
    "FC VAR": {"manager": "Varun Kadikar", "short": "VAR", "id": "varun", "city": "San Francisco", "role": "Co-Commissioner"},
    "youngmoon": {"manager": "Young Moon", "short": "YOU", "id": "young", "city": "Washington D.C.", "role": "Manager"},
    "Toadenham Frogspur": {"manager": "Ari Diddams", "short": "ARI", "id": "ari", "city": "San Diego", "role": "Manager"},
    "Wallalujah": {"manager": "Nilay Agarwalla", "short": "WAL", "id": "nilay", "city": "New York City", "role": "Manager"},
    "Traderjoe18": {"manager": "Joseph Lei", "short": "JOS", "id": "joseph", "city": "San Diego", "role": "Manager"},
    "Birds & Bees FC": {"manager": "Suda", "short": "SUD", "id": "suda", "city": "San Francisco", "role": "Manager"},
    "Birds and Bees FC": {"manager": "Suda", "short": "SUD", "id": "suda", "city": "San Francisco", "role": "Manager"},
    "Arnie-senal": {"manager": "Arnav Jain", "short": "ARN", "id": "arnav", "city": "Los Angeles", "role": "Manager"},
    "WayneRooney10": {"manager": "Danny Najafian", "short": "DAN", "id": "danny", "city": "Los Angeles", "role": "Manager"},
    "waynerooney10": {"manager": "Danny Najafian", "short": "DAN", "id": "danny", "city": "Los Angeles", "role": "Manager"},
    "FC Purulona": {"manager": "Puru Lohiya", "short": "PUR", "id": "puru", "city": "Denver", "role": "Manager"},
    "sduvuuru": {"manager": "Subba Duvuuru", "short": "SUB", "id": "subba", "city": "San Diego", "role": "Manager"},
    "Estimated Profit": {"manager": "Isaac Owen", "short": "ISA", "id": "isaac", "city": "New York City", "role": "Manager"},
    "seanbridges7": {"manager": "Sean Bridges", "short": "SEA", "id": "sean", "city": "New York City", "role": "Manager (Debutant)"},
    "MOO FC": {"manager": "Rahul Mohankumar", "short": "RAH", "id": "rahul", "city": "San Francisco", "role": "Manager (Debutant)"},
    "Smip Estonian": {"manager": "Shawn Hussain", "short": "SMI", "id": "shawn", "city": "San Francisco", "role": "Co-Commissioner"}
}


def get_meta(team_name: str) -> dict:
    return TEAM_MANAGER_MAP.get(team_name, {
        "manager": team_name,
        "short": team_name[:3].upper(),
        "id": team_name.lower().replace(" ", ""),
        "city": "USA",
        "role": "Manager"
    })


def main():
    league_id = os.getenv("FANTRAX_LEAGUE_ID", "iku2an1nmryzcfa2")
    cookie_path = os.path.join(PROJECT_ROOT, "fantraxloggedin.cookie")

    print(f"Connecting to Fantrax API for League ID: {league_id}...")
    client = FantraxClient(league_id=league_id, cookie_path=cookie_path)

    # 1. Fetch Real Matchups & Table
    matchups_df = client.get_matchups(through_week=38, as_dataframe=True)
    table_df = client.get_league_table()
    eff_df = client.get_league_manager_efficiency()
    opt_df = client.get_optimal_standings()
    median_df = calculate_median_standings(matchups_df)

    completed_gws = sorted(matchups_df[matchups_df["score"] > 0]["week"].unique().tolist())
    latest_gw = max(completed_gws) if completed_gws else 1
    print(f"Fetched {len(matchups_df)} matchups across 38 matchweeks. Completed GWs: {completed_gws}")

    # 2. Build Structured Real Standings
    standings_list = []
    for rank, (team, row) in enumerate(table_df.iterrows(), 1):
        meta = get_meta(team)
        eff_row = eff_df.loc[team] if team in eff_df.index else None
        opt_row = opt_df.loc[team] if team in opt_df.index else None
        median_row = median_df.loc[team] if team in median_df.index else None

        # Calculate form (last 5 results for completed matchweeks)
        team_matches = matchups_df[(matchups_df["team"] == team) & (matchups_df["week"].isin(completed_gws))].sort_values("week")
        form = team_matches["result"].tolist()[-5:] if not team_matches.empty else ["-"]

        max_pf = round(float(eff_row["avg_max_score"] * row["wins"] + eff_row["avg_max_score"] * row["losses"] if eff_row is not None else row["fpts_for"]), 2)
        if eff_row is not None and "total_max_points" in eff_row:
            max_pf = round(float(eff_row["total_max_points"]), 2)
        elif eff_row is not None and "avg_max_score" in eff_row:
            max_pf = round(float(eff_row["avg_max_score"] * len(completed_gws)), 2)

        actual_pf = round(float(row["fpts_for"]), 2)
        eff_val = round((actual_pf / max_pf * 100), 1) if max_pf > 0 else 100.0
        bench_pts = round(max(0.0, max_pf - actual_pf), 2)
        diff_val = round(float(row["fpts_for"] - row["fpts_against"]), 2)
        diff_str = f"+{diff_val}" if diff_val >= 0 else str(diff_val)

        standings_list.append({
            "rank": rank,
            "managerId": meta["id"],
            "name": meta["manager"],
            "team": team,
            "p": int(row["wins"] + row["draws"] + row["losses"]),
            "w": int(row["wins"]),
            "d": int(row["draws"]),
            "l": int(row["losses"]),
            "pf": actual_pf,
            "pa": round(float(row["fpts_against"]), 2),
            "diff": diff_str,
            "pts": int(row["points"]),
            "form": form,
            "maxPf": max_pf,
            "eff": eff_val,
            "benchPts": bench_pts,
            "medianRecord": str(median_row["record"]) if median_row is not None else f"{int(row['wins'])}-{int(row['draws'])}-{int(row['losses'])}",
            "optimalRank": int(opt_row["rank"]) if opt_row is not None and "rank" in opt_row else rank
        })

    # 3. Build Matchups by Gameweek (1 to 38)
    gameweek_matchups = {}
    weekly_high_scores = []

    # CL Matchups definition from PDF (GW 6, 11, 16, 21, 26)
    cl_pairs = {
        6: [("Traderjoe18", "FC VAR"), ("Arnie-senal", "Smip Estonian"), ("youngmoon", "Toadenham Frogspur")],
        11: [("Traderjoe18", "Smip Estonian"), ("Arnie-senal", "Toadenham Frogspur"), ("youngmoon", "FC VAR")],
        16: [("Traderjoe18", "Toadenham Frogspur"), ("Arnie-senal", "youngmoon"), ("Smip Estonian", "FC VAR")],
        21: [("Traderjoe18", "youngmoon"), ("Arnie-senal", "FC VAR"), ("Toadenham Frogspur", "Smip Estonian")],
        26: [("Traderjoe18", "Arnie-senal"), ("youngmoon", "Smip Estonian"), ("FC VAR", "Toadenham Frogspur")]
    }

    for gw in range(1, 39):
        gw_df = matchups_df[matchups_df["week"] == gw]
        if gw_df.empty:
            continue

        gw_list = []
        seen = set()
        for _, r in gw_df.iterrows():
            t = r["team"]
            opp = r["opponent"]
            pair = tuple(sorted([t, opp]))
            if pair in seen:
                continue
            seen.add(pair)

            meta_home = get_meta(t)
            meta_away = get_meta(opp)

            # Check if Champions League designated matchup
            is_cl = False
            if gw in cl_pairs:
                for p1, p2 in cl_pairs[gw]:
                    if (t == p1 and opp == p2) or (t == p2 and opp == p1):
                        is_cl = True
                        break

            gw_list.append({
                "home": meta_home["manager"],
                "homeTeam": t,
                "homeScore": round(float(r["score"]), 2),
                "away": meta_away["manager"],
                "awayTeam": opp,
                "awayScore": round(float(r["opponent_score"]), 2),
                "clMatch": is_cl
            })

        gameweek_matchups[gw] = gw_list

        # If completed GW, compute weekly high score
        if gw in completed_gws:
            completed_in_gw = gw_df[gw_df["score"] > 0]
            if not completed_in_gw.empty:
                best_row = completed_in_gw.sort_values("score", ascending=False).iloc[0]
                best_meta = get_meta(best_row["team"])
                weekly_high_scores.append({
                    "gw": gw,
                    "manager": best_meta["manager"],
                    "team": best_row["team"],
                    "score": round(float(best_row["score"]), 2),
                    "prize": "$10"
                })

    # 4. Read complete PDF handbook components (bylaws, scoring, history)
    # Build complete consolidated real dataset JS
    js_content = f"""/**
 * The Gentlemen's Invitational: Fantasy Prem 2026-27
 * OFFICIAL LEAGUE DATASET (Directly connected to Fantrax League: {league_id})
 */

const LEAGUE_DATA = {{
  metadata: {{
    name: "The Gentlemen’s Invitational",
    subtitle: "Fantasy Prem 2026-27 — Official League Headquarters",
    season: "2026-2027",
    edition: "4th Annual Edition",
    leagueId: "{league_id}",
    commissioners: ["Shayan Hussain", "Varun Kadikar"],
    memberCount: 14,
    cities: [
      "San Diego",
      "Los Angeles",
      "San Francisco",
      "New York City",
      "Washington D.C.",
      "Denver"
    ],
    dates: {{
      draftDay: "August 17, 2026 (7:00 PM PT / 10:00 PM ET)",
      kickoff: "August 21, 2026",
      finalMatchday: "May 30, 2027"
    }},
    buyIn: 100,
    totalPrizePool: 1400,
    punishment: "The 24-Hour IHOP Pancake Challenge (Last Place Finisher)"
  }},

  prizes: [
    {{ rank: "Regular Season Winner", amount: 400, icon: "🥇", type: "silverware", desc: "Crown of the 38-week regular season endurance race" }},
    {{ rank: "Champions League Winner", amount: 200, icon: "⭐", type: "silverware", desc: "Top 5 from previous year + reigning CL Champ battle" }},
    {{ rank: "Lingineni Cup Champion", amount: 170, icon: "🏆", type: "silverware", desc: "14-manager single elimination knockout tournament" }},
    {{ rank: "Regular Season Runner-Up", amount: 150, icon: "🥈", type: "podium", desc: "2nd place regular season finish" }},
    {{ rank: "Regular Season 3rd Place", amount: 100, icon: "🥉", type: "podium", desc: "3rd place regular season podium" }},
    {{ rank: "Weekly High Score", amount: 380, icon: "⚡", type: "weekly", desc: "$10 per gameweek across all 38 gameweeks" }}
  ],

  managers: [
    {{
      id: "varun",
      name: "Varun Kadikar",
      teamName: "FC VAR",
      shortName: "VAR",
      city: "San Francisco",
      role: "Co-Commissioner",
      status: "Active",
      accolades: ["25-26 League Champion", "24-25 Champions League Winner"],
      careerMoney: 580,
      careerRecord: {{ w: 67, d: 0, l: 43, pts: 201, weeks: 110, ppg: 1.83 }},
      bio: "Defending League Champion. Master tactician known for ruthless FAAB bidding and relentless optimal roster navigation."
    }},
    {{
      id: "shawn",
      name: "Shawn Hussain",
      teamName: "Smip Estonian",
      shortName: "SMI",
      city: "San Francisco",
      role: "Co-Commissioner",
      status: "Active",
      accolades: ["24-25 League Champion", "25-26 Champions League Winner"],
      careerMoney: 365,
      careerRecord: {{ w: 62, d: 0, l: 48, pts: 186, weeks: 110, ppg: 1.69 }},
      bio: "Reigning Champions League holder and former regular season champion. A stalwart of managerial excellence."
    }},
    {{
      id: "nilay",
      name: "Nilay Agarwalla",
      teamName: "Wallalujah",
      shortName: "WAL",
      city: "New York City",
      role: "Manager",
      status: "Active",
      accolades: ["25-26 Lingineni Cup Champion"],
      careerMoney: 215,
      careerRecord: {{ w: 44, d: 0, l: 32, pts: 132, weeks: 76, ppg: 1.74 }},
      bio: "Secured Wallalujah's maiden silverware in the 25-26 Lingineni Cup with a sublime knockout run."
    }},
    {{
      id: "ari",
      name: "Ari Diddams",
      teamName: "Toadenham Frogspur",
      shortName: "ARI",
      city: "San Diego",
      role: "Manager",
      status: "Active",
      accolades: ["25-26 League Runner-Up"],
      careerMoney: 180,
      careerRecord: {{ w: 62, d: 2, l: 46, pts: 188, weeks: 110, ppg: 1.71 }},
      bio: "Perennial podium contender boasting the 2nd highest points per week among founding 3-year veterans."
    }},
    {{
      id: "arnav",
      name: "Arnav Jain",
      teamName: "Arnie-senal",
      shortName: "ARN",
      city: "Los Angeles",
      role: "Manager",
      status: "Active",
      accolades: ["23-24 Playoff Champion", "IHOP Challenge Legend (24-25)"],
      careerMoney: 175,
      careerRecord: {{ w: 51, d: 0, l: 59, pts: 153, weeks: 110, ppg: 1.39 }},
      bio: "Inaugural season playoff champion who survived the grueling 24-hour IHOP challenge in 2025 to return stronger than ever."
    }},
    {{
      id: "young",
      name: "Young Moon",
      teamName: "youngmoon",
      shortName: "YOU",
      city: "Washington D.C.",
      role: "Manager",
      status: "Active",
      accolades: ["25-26 3rd Place Podium"],
      careerMoney: 150,
      careerRecord: {{ w: 52, d: 1, l: 57, pts: 157, weeks: 110, ppg: 1.43 }},
      bio: "Ascended into elite territory with a magnificent 3rd place finish in 25-26, clinching Champions League qualification."
    }},
    {{
      id: "puru",
      name: "Puru Lohiya",
      teamName: "FC Purulona",
      shortName: "PUR",
      city: "Denver",
      role: "Manager",
      status: "Active",
      accolades: ["24-25 Lingineni Cup Champion"],
      careerMoney: 110,
      careerRecord: {{ w: 50, d: 0, l: 60, pts: 150, weeks: 110, ppg: 1.36 }},
      bio: "Inaugural Lingineni Cup champion in 24-25. Known for giant-killing knockout heroics and midfield mastery."
    }},
    {{
      id: "suda",
      name: "Suda",
      teamName: "Birds and Bees FC",
      shortName: "SUD",
      city: "San Francisco",
      role: "Manager",
      status: "Active",
      accolades: ["Top 4 Finish (24-25)"],
      careerMoney: 80,
      careerRecord: {{ w: 58, d: 0, l: 52, pts: 174, weeks: 110, ppg: 1.58 }},
      bio: "Consistent top-half contender with explosive weekly scoring capable of blowing past any squad in the league."
    }},
    {{
      id: "joseph",
      name: "Joseph Lei",
      teamName: "Traderjoe18",
      shortName: "JOS",
      city: "San Diego",
      role: "Manager",
      status: "Active",
      accolades: ["Champions League Qualifier (26-27)", "3rd Place Finish (23-24)"],
      careerMoney: 40,
      careerRecord: {{ w: 54, d: 2, l: 54, pts: 164, weeks: 110, ppg: 1.49 }},
      bio: "Veteran manager who punched his ticket to the 2026-27 Champions League via a resilient 4th place finish."
    }},
    {{
      id: "danny",
      name: "Danny Najafian",
      teamName: "waynerooney10",
      shortName: "DAN",
      city: "Los Angeles",
      role: "Manager",
      status: "Active",
      accolades: ["6th Place Debut (24-25)"],
      careerMoney: 20,
      careerRecord: {{ w: 38, d: 1, l: 37, pts: 115, weeks: 76, ppg: 1.51 }},
      bio: "Dangerous tactician boasting a positive career record across two seasons in the league."
    }},
    {{
      id: "isaac",
      name: "Isaac Owen",
      teamName: "Estimated Profit",
      shortName: "ISA",
      city: "New York City",
      role: "Manager",
      status: "Active",
      accolades: ["25-26 Survivor"],
      careerMoney: 20,
      careerRecord: {{ w: 16, d: 0, l: 22, pts: 48, weeks: 38, ppg: 1.26 }},
      bio: "Entering sophomore year with valuable premier league experience and eyes set on tournament silverware."
    }},
    {{
      id: "subba",
      name: "Subba Duvuuru",
      teamName: "sduvuuru",
      shortName: "SUB",
      city: "San Diego",
      role: "Manager",
      status: "Active",
      accolades: ["25-26 Lingineni Cup Finalist"],
      careerMoney: 10,
      careerRecord: {{ w: 37, d: 1, l: 38, pts: 112, weeks: 76, ppg: 1.47 }},
      bio: "Cup run specialist who stormed to the Lingineni Cup final in 25-26 with clutch defensive setups."
    }},
    {{
      id: "rahul",
      name: "Rahul Mohankumar",
      teamName: "MOO FC",
      shortName: "RAH",
      city: "San Francisco",
      role: "Manager (Debutant)",
      status: "Active",
      accolades: ["2026-27 New Manager"],
      careerMoney: 0,
      careerRecord: {{ w: 0, d: 0, l: 0, pts: 0, weeks: 0, ppg: 0.00 }},
      bio: "Making his world stage debut in 2026-27. Replaces relegated spot with sky-high ambitions and fresh tactical ideas."
    }},
    {{
      id: "sean",
      name: "Sean Bridges",
      teamName: "seanbridges7",
      shortName: "SEA",
      city: "New York City",
      role: "Manager (Debutant)",
      status: "Active",
      accolades: ["2026-27 New Manager"],
      careerMoney: 0,
      careerRecord: {{ w: 0, d: 0, l: 0, pts: 0, weeks: 0, ppg: 0.00 }},
      bio: "New entrant for the 2026-27 campaign eager to challenge the established guard and avoid the IHOP gauntlet."
    }}
  ],

  currentSeason: {{
    currentGameweek: {latest_gw},
    completedGameweeks: {json.dumps(completed_gws)},
    standings: {json.dumps(standings_list, indent=6)},
    weeklyHighScores: {json.dumps(weekly_high_scores, indent=6)},
    gameweekMatchups: {json.dumps(gameweek_matchups, indent=6)}
  }},

  championsLeague: {{
    qualifiers: [
      {{ name: "Varun Kadikar", team: "FC VAR", reason: "2025-26 League Champion (1st)", code: "A6" }},
      {{ name: "Ari Diddams", team: "Toadenham Frogspur", reason: "2025-26 League Runner-Up (2nd)", code: "A4" }},
      {{ name: "Young Moon", team: "youngmoon", reason: "2025-26 3rd Place", code: "A3" }},
      {{ name: "Joseph Lei", team: "Traderjoe18", reason: "2025-26 4th Place", code: "A1" }},
      {{ name: "Arnav Jain", team: "Arnie-senal", reason: "2025-26 5th Place", code: "A2" }},
      {{ name: "Shawn Hussain", team: "Smip Estonian", reason: "2025-26 Champions League Winner", code: "A5" }}
    ],
    groupSchedule: [
      {{ gw: 6, m1: "Joseph (Traderjoe18) vs Varun (FC VAR)", m2: "Arnav (Arnie-senal) vs Shawn (Smip Estonian)", m3: "Young (youngmoon) vs Ari (Toadenham Frogspur)" }},
      {{ gw: 11, m1: "Joseph (Traderjoe18) vs Shawn (Smip Estonian)", m2: "Arnav (Arnie-senal) vs Ari (Toadenham Frogspur)", m3: "Young (youngmoon) vs Varun (FC VAR)" }},
      {{ gw: 16, m1: "Joseph (Traderjoe18) vs Ari (Toadenham Frogspur)", m2: "Arnav (Arnie-senal) vs Young (youngmoon)", m3: "Shawn (Smip Estonian) vs Varun (FC VAR)" }},
      {{ gw: 21, m1: "Joseph (Traderjoe18) vs Young (youngmoon)", m2: "Arnav (Arnie-senal) vs Varun (FC VAR)", m3: "Ari (Toadenham Frogspur) vs Shawn (Smip Estonian)" }},
      {{ gw: 26, m1: "Joseph (Traderjoe18) vs Arnav (Arnie-senal)", m2: "Young (youngmoon) vs Shawn (Smip Estonian)", m3: "Varun (FC VAR) vs Ari (Toadenham Frogspur)" }}
    ],
    knockoutSchedule: [
      {{ round: "Semi-Finals", gws: "GW 31 & GW 33", format: "Two-Legged Aggregate", m1: "Group Winner (1st) vs 4th Place", m2: "Runner-Up (2nd) vs 3rd Place" }},
      {{ round: "Champions League Final", gws: "GW 36", format: "One-Legged Match", m1: "Semi-Final 1 Winner vs Semi-Final 2 Winner" }}
    ],
    currentGroupTable: [
      {{ pos: 1, name: "Varun Kadikar", team: "FC VAR", w: 0, d: 0, l: 0, pts: 0, pf: 0.0, pa: 0.0 }},
      {{ pos: 2, name: "Shawn Hussain", team: "Smip Estonian", w: 0, d: 0, l: 0, pts: 0, pf: 0.0, pa: 0.0 }},
      {{ pos: 3, name: "Young Moon", team: "youngmoon", w: 0, d: 0, l: 0, pts: 0, pf: 0.0, pa: 0.0 }},
      {{ pos: 4, name: "Arnav Jain", team: "Arnie-senal", w: 0, d: 0, l: 0, pts: 0, pf: 0.0, pa: 0.0 }},
      {{ pos: 5, name: "Ari Diddams", team: "Toadenham Frogspur", w: 0, d: 0, l: 0, pts: 0, pf: 0.0, pa: 0.0 }},
      {{ pos: 6, name: "Joseph Lei", team: "Traderjoe18", w: 0, d: 0, l: 0, pts: 0, pf: 0.0, pa: 0.0 }}
    ]
  }},

  lingineniCup: {{
    format: "Single elimination bracket based on last season's finishes. Bottom 4 contest Round 1, Top 4 receive Byes to Quarter-Finals.",
    rounds: [
      {{ name: "Round 1", gw: "GW 9", matches: [
        {{ id: "R1_M1", p1: "Suda (Birds and Bees FC)", p2: "Rahul Mohankumar (MOO FC)", winner: "TBD" }},
        {{ id: "R1_M2", p1: "Sean Bridges (seanbridges7)", p2: "Isaac Owen (Estimated Profit)", winner: "TBD" }}
      ]}},
      {{ name: "Round 2", gw: "GW 14", matches: [
        {{ id: "R2_M1", p1: "Winner (Suda/Rahul)", p2: "Nilay Agarwalla (Wallalujah)", winner: "TBD" }},
        {{ id: "R2_M2", p1: "Shawn Hussain (Smip Estonian)", p2: "Arnav Jain (Arnie-senal)", winner: "TBD" }},
        {{ id: "R2_M3", p1: "Danny Najafian (waynerooney10)", p2: "Puru Lohiya (FC Purulona)", winner: "TBD" }},
        {{ id: "R2_M4", p1: "Winner (Sean/Isaac)", p2: "Subba Duvuuru (sduvuuru)", winner: "TBD" }}
      ]}},
      {{ name: "Quarter-Finals", gw: "GW 19", matches: [
        {{ id: "QF1", p1: "Ari Diddams (Bye)", p2: "Winner R2_M1", winner: "TBD" }},
        {{ id: "QF2", p1: "Joseph Lei (Bye)", p2: "Winner R2_M2", winner: "TBD" }},
        {{ id: "QF3", p1: "Young Moon (Bye)", p2: "Winner R2_M3", winner: "TBD" }},
        {{ id: "QF4", p1: "Varun Kadikar (Bye)", p2: "Winner R2_M4", winner: "TBD" }}
      ]}},
      {{ name: "Semi-Finals", gw: "GW 24 & 29 (2-Legged)", matches: [
        {{ id: "SF1", p1: "Winner QF1", p2: "Winner QF2", winner: "TBD" }},
        {{ id: "SF2", p1: "Winner QF3", p2: "Winner QF4", winner: "TBD" }}
      ]}},
      {{ name: "Final", gw: "GW 34", matches: [
        {{ id: "FINAL", p1: "Winner SF1", p2: "Winner SF2", winner: "TBD" }}
      ]}}
    ]
  }},

  bylaws: [
    {{
      article: "Article I",
      title: "League Structure & Governance",
      sections: [
        {{
          subtitle: "1. Commissioner Authority & Discretionary Powers",
          content: "The Commissioner serves as the executive administrator responsible for day-to-day league operations, maintaining Fantrax platform settings, processing transactions, and resolving unforeseen disputes.\\n\\n• Commissioner Discretion (Gray Areas): Situations involving ambiguity, edge cases, technical glitches, unwritten scenarios, or subjective rule interpretations (e.g., assessing manager inactivity, investigating potential trade collusion, or handling unexpected platform errors) fall under the direct authority and discretion of the Commissioner. The Commissioner’s primary goal in these gray-area rulings is to preserve competitive fairness and league integrity."
        }},
        {{
          subtitle: "2. League Voting & Rule Amendments",
          content: "For rulings or proposals that impact the core structure of the entire league, the decision will be put to a league-wide vote.\\n\\n• Voting Standard: All league-wide votes operate under a simple majority rule (>50% of active managers).\\n• Scope of Voting: A majority vote is required for mid-season/off-season amendments to this Constitution, adjustments to scoring rules, roster limits, or financial structures (FAAB/buy-in).\\n• Tiebreakers: In the event of a tied vote on a league proposal, the Commissioner’s vote acts as the decisive tiebreaker."
        }}
      ]
    }},
    {{
      article: "Article II",
      title: "Rosters & Positional Eligibility",
      sections: [
        {{
          subtitle: "1. Roster Composition",
          content: "Squads consist of 17 total players (11 Starters, 5 Bench Spots, 1 Injured Reserve), confirmed following the draft on August 17."
        }},
        {{
          subtitle: "2. Multi-Positionality Policy",
          content: "• Dual Eligibility: If a player is assigned multiple positions in real life by the Fantrax data feed, the manager will be able to start that player in either eligible position slot in their active lineup.\\n• Mid-Season Adjustments: The assumption is that designations added by Fantrax mid-season are valid immediately upon update. Whether or not Fantrax actually implements this will be revealed during the season."
        }}
      ]
    }},
    {{
      article: "Article III",
      title: "Free Agency & Waiver Wire (FAAB)",
      sections: [
        {{
          subtitle: "1. FAAB Allocation & Bidding",
          content: "• Season Budget: Each team receives a Free Agent Acquisition Budget (FAAB) of $200.00 for the entire season.\\n• Minimum Bid: The minimum allowed bid is $0.00.\\n• Bidding Format: Blind bidding runs twice weekly via Fantrax, followed by standard continuous waivers/free agency until gameweek lockout."
        }},
        {{
          subtitle: "2. Tiebreakers",
          content: "• Randomization: If two or more managers submit identical winning FAAB dollar bids for the same player, the tie will be broken via Fantrax’s automated random generator tiebreaker system."
        }}
      ]
    }},
    {{
      article: "Article IV",
      title: "Trades & Transaction Integrity",
      sections: [
        {{
          subtitle: "1. Trade Rules & Deadlines",
          content: "• Trade Veto Procedure: Trades are subject to a 24-hour veto window following the time of acceptance. A trade will be reversed if 10 out of 14 managers submit a written veto request to the Commissioner within this 24-hour period. In the absence of such a veto, trades will execute automatically. The Commissioner retains final authority to intervene in cases of clear collusion (see Article V).\\n• Trade Deadline: The trade deadline is set for the conclusion of Gameweek 34. No trades may take place after this cutoff.\\n• FAAB Trading: Managers are permitted to trade FAAB dollars alongside players in trade offers, provided neither team exceeds the max available cap."
        }}
      ]
    }},
    {{
      article: "Article V",
      title: "Competitive Integrity, Collusion, & Tanking",
      sections: [
        {{
          subtitle: "1. Anti-Collusion Policy",
          content: "• Definition: Collusion includes, but is not limited to: intent to pool assets, one-sided trades favoring a contender to share winnings, benching key starters to intentionally gift wins, or loaning players across teams. Loaning players as part of a larger trade is permitted, but temporary trades of players that provide no immediate benefit to both teams are considered collusive and are prohibited.\\n• Penalties: Any trade deemed collusive by the Commissioner will be immediately reversed. Offending managers face immediate forfeit of matches, loss of FAAB budget, or expulsion from the league without a refund in severe scenarios."
        }},
        {{
          subtitle: "2. Anti-Tanking & Bench Integrity",
          content: "• Active Lineups: Every manager must attempt to submit a full, active starting XI every single Gameweek. Intentional benching of healthy elite players, leaving blank starter spots when fit bench players are available, or starting injured/suspended players deliberately to lose a matchup is strictly prohibited. Note that this rule applies specifically to deliberate tanking; occasional lineup misses due to accidental absences (e.g., sleeping through a kickoff) do not constitute a violation, provided they are not part of a pattern of intentional neglect."
        }}
      ]
    }},
    {{
      article: "Article VI",
      title: "Participation & Manager Activity",
      sections: [
        {{
          subtitle: "1. Activity Requirements",
          content: "Managers must actively manage their squads, including submitting starting lineups, managing rosters, and responding to league communications."
        }},
        {{
          subtitle: "2. Disciplinary Escalation",
          content: "Non-responsive or inactive managers will be subject to a 2-step protocol:\\n• Step 1 — Formal Warning: The Commissioner will issue an official written warning.\\n• Step 2 — Removal: If a manager displays further lack of participation, the Commissioner reserves the right to remove the manager. The Commissioner will then lock the team's roster and set the optimal starting lineup (based solely on projections) weekly until a replacement is found."
        }}
      ]
    }},
    {{
      article: "Article VII",
      title: "Last Place Penalty — The 24-Hour IHOP Challenge",
      sections: [
        {{
          subtitle: "1. Rules of the Challenge",
          content: "The manager who finishes dead-last in the standings at the end of the season must complete The 24-Hour IHOP Challenge.\\n\\n• The Goal: The losing manager must stay inside an International House of Pancakes (IHOP) restaurant for 24 continuous hours.\\n• Time Reductions: For every pancake eaten, 1 hour is deducted from the remaining time penalty.\\n• Proof & Verification: The attempt must be tracked via live video check-ins and receipt evidence. Failure to complete the penalty results in immediate expulsion from the league."
        }}
      ]
    }},
    {{
      article: "Article VIII",
      title: "Edge Cases & System Glitches",
      sections: [
        {{
          subtitle: "1. Fantrax Outages",
          content: "If a proven technical glitch on Fantrax prevents a lineup change, the manager must contact the Commissioner before kick-off with proof. The Commissioner may manually update the lineup."
        }}
      ]
    }},
    {{
      article: "Article IX",
      title: "Scoring & Matchdays",
      sections: [
        {{
          subtitle: "1. Format & Points System",
          content: "• Season Duration: Competition runs from matchday 1 through matchday 38 of the Premier League season.\\n• Match Format: Managers compete in weekly head-to-head matchups and must submit an 11-man starting lineup before kickoff.\\n• Scoring: Points are awarded based on real-life player performance and actions during fixtures.\\n• Standings: The winner of each weekly head-to-head matchup receives 3 points toward the overall league standings (3 for a win, 1 for a draw, 0 for a loss)."
        }}
      ]
    }}
  ],

  scoringMatrix: {{
    G: [
      {{ stat: "Aerials Won (AER)", pts: 1.0, type: "defensive" }},
      {{ stat: "Assists (AT)", pts: 7.0, type: "attacking" }},
      {{ stat: "Clean Sheets (CS)", pts: 8.0, type: "defensive" }},
      {{ stat: "Dispossessed (DIS)", pts: -0.5, type: "negative" }},
      {{ stat: "Effective Clearances (CLR)", pts: 0.25, type: "defensive" }},
      {{ stat: "Goals (G)", pts: 10.0, type: "attacking" }},
      {{ stat: "Goals Against (GAO)", pts: -2.0, type: "negative" }},
      {{ stat: "High Claims Succeeded (HCS)", pts: 1.0, type: "goalkeeping" }},
      {{ stat: "Interceptions (INT)", pts: 1.0, type: "defensive" }},
      {{ stat: "Key Passes (KP)", pts: 2.0, type: "attacking" }},
      {{ stat: "Own Goals (OG)", pts: -5.0, type: "negative" }},
      {{ stat: "Penalty Kick Saves (PKS)", pts: 8.0, type: "goalkeeping" }},
      {{ stat: "Red Cards (RC)", pts: -7.0, type: "negative" }},
      {{ stat: "Saves (SV)", pts: 2.0, type: "goalkeeping" }},
      {{ stat: "Shots on Target (SOT)", pts: 2.0, type: "attacking" }},
      {{ stat: "Smothers (SM)", pts: 1.0, type: "goalkeeping" }},
      {{ stat: "Successful Dribbles (COS)", pts: 1.0, type: "attacking" }},
      {{ stat: "Tackles Won (TKW)", pts: 1.0, type: "defensive" }},
      {{ stat: "Yellow Cards (YC)", pts: -2.0, type: "negative" }}
    ],
    D: [
      {{ stat: "Aerials Won (AER)", pts: 1.0, type: "defensive" }},
      {{ stat: "Assists (AT)", pts: 7.0, type: "attacking" }},
      {{ stat: "Clean Sheets (CS)", pts: 6.0, type: "defensive" }},
      {{ stat: "Effective Clearances (CLR)", pts: 0.25, type: "defensive" }},
      {{ stat: "Goals (G)", pts: 10.0, type: "attacking" }},
      {{ stat: "Goals Against (GAO)", pts: -2.0, type: "negative" }},
      {{ stat: "Accurate Crosses (ACNC)", pts: 1.0, type: "attacking" }},
      {{ stat: "Blocked Shots (BS)", pts: 1.0, type: "defensive" }},
      {{ stat: "Dispossessed (DIS)", pts: -0.5, type: "negative" }},
      {{ stat: "Interceptions (INT)", pts: 1.0, type: "defensive" }},
      {{ stat: "Key Passes (KP)", pts: 2.0, type: "attacking" }},
      {{ stat: "Own Goals (OG)", pts: -5.0, type: "negative" }},
      {{ stat: "Penalty Kicks Drawn (PKD)", pts: 2.0, type: "attacking" }},
      {{ stat: "Penalty Kicks Missed (PKM)", pts: -4.0, type: "negative" }},
      {{ stat: "Red Cards (RC)", pts: -7.0, type: "negative" }},
      {{ stat: "Shots on Target (SOT)", pts: 2.0, type: "attacking" }},
      {{ stat: "Successful Dribbles (COS)", pts: 1.0, type: "attacking" }},
      {{ stat: "Tackles Won (TKW)", pts: 1.0, type: "defensive" }},
      {{ stat: "Yellow Cards (YC)", pts: -2.0, type: "negative" }}
    ],
    M: [
      {{ stat: "Aerials Won (AER)", pts: 0.5, type: "defensive" }},
      {{ stat: "Assists (AT)", pts: 6.0, type: "attacking" }},
      {{ stat: "Clean Sheets (CS)", pts: 1.0, type: "defensive" }},
      {{ stat: "Goals (G)", pts: 9.0, type: "attacking" }},
      {{ stat: "Accurate Crosses (ACNC)", pts: 1.0, type: "attacking" }},
      {{ stat: "Blocked Shots (BS)", pts: 1.0, type: "defensive" }},
      {{ stat: "Dispossessed (DIS)", pts: -0.5, type: "negative" }},
      {{ stat: "Interceptions (INT)", pts: 1.0, type: "defensive" }},
      {{ stat: "Key Passes (KP)", pts: 2.0, type: "attacking" }},
      {{ stat: "Own Goals (OG)", pts: -5.0, type: "negative" }},
      {{ stat: "Penalty Kicks Drawn (PKD)", pts: 2.0, type: "attacking" }},
      {{ stat: "Penalty Kicks Missed (PKM)", pts: -4.0, type: "negative" }},
      {{ stat: "Red Cards (RC)", pts: -7.0, type: "negative" }},
      {{ stat: "Shots on Target (SOT)", pts: 2.0, type: "attacking" }},
      {{ stat: "Successful Dribbles (COS)", pts: 1.0, type: "attacking" }},
      {{ stat: "Tackles Won (TKW)", pts: 1.0, type: "defensive" }},
      {{ stat: "Yellow Cards (YC)", pts: -2.0, type: "negative" }}
    ],
    F: [
      {{ stat: "Aerials Won (AER)", pts: 0.5, type: "defensive" }},
      {{ stat: "Assists (AT)", pts: 6.0, type: "attacking" }},
      {{ stat: "Goals (G)", pts: 9.0, type: "attacking" }},
      {{ stat: "Accurate Crosses (ACNC)", pts: 1.0, type: "attacking" }},
      {{ stat: "Blocked Shots (BS)", pts: 1.0, type: "defensive" }},
      {{ stat: "Dispossessed (DIS)", pts: -0.5, type: "negative" }},
      {{ stat: "Interceptions (INT)", pts: 1.0, type: "defensive" }},
      {{ stat: "Key Passes (KP)", pts: 2.0, type: "attacking" }},
      {{ stat: "Own Goals (OG)", pts: -5.0, type: "negative" }},
      {{ stat: "Penalty Kicks Drawn (PKD)", pts: 2.0, type: "attacking" }},
      {{ stat: "Penalty Kicks Missed (PKM)", pts: -4.0, type: "negative" }},
      {{ stat: "Red Cards (RC)", pts: -7.0, type: "negative" }},
      {{ stat: "Shots on Target (SOT)", pts: 2.0, type: "attacking" }},
      {{ stat: "Successful Dribbles (COS)", pts: 1.0, type: "attacking" }},
      {{ stat: "Tackles Won (TKW)", pts: 1.0, type: "defensive" }},
      {{ stat: "Yellow Cards (YC)", pts: -2.0, type: "negative" }}
    ]
  }},

  history: {{
    allTimeRankings: [
      {{ rank: 1, player: "Rithik", w: 21, d: 0, l: 13, pts: 63, weeks: 34, ppw: 1.85, status: "Relegated 23-24" }},
      {{ rank: 2, player: "Varun Kadikar", w: 67, d: 0, l: 43, pts: 201, weeks: 110, ppw: 1.83, status: "Active" }},
      {{ rank: 3, player: "Zach", w: 64, d: 1, l: 45, pts: 193, weeks: 110, ppw: 1.75, status: "Relegated 25-26" }},
      {{ rank: 4, player: "Nilay Agarwalla", w: 44, d: 0, l: 32, pts: 132, weeks: 76, ppw: 1.74, status: "Active" }},
      {{ rank: 5, player: "Ari Diddams", w: 62, d: 2, l: 46, pts: 188, weeks: 110, ppw: 1.71, status: "Active" }},
      {{ rank: 6, player: "Shawn Hussain", w: 62, d: 0, l: 48, pts: 186, weeks: 110, ppw: 1.69, status: "Active" }},
      {{ rank: 7, player: "Suda", w: 58, d: 0, l: 52, pts: 174, weeks: 110, ppw: 1.58, status: "Active" }},
      {{ rank: 8, player: "Danny Najafian", w: 38, d: 1, l: 37, pts: 115, weeks: 76, ppw: 1.51, status: "Active" }},
      {{ rank: 9, player: "Joseph Lei", w: 54, d: 2, l: 54, pts: 164, weeks: 110, ppw: 1.49, status: "Active" }},
      {{ rank: 10, player: "Subba Duvuuru", w: 37, d: 1, l: 38, pts: 112, weeks: 76, ppw: 1.47, status: "Active" }},
      {{ rank: 11, player: "Young Moon", w: 52, d: 1, l: 57, pts: 157, weeks: 110, ppw: 1.43, status: "Active" }},
      {{ rank: 12, player: "Arnav Jain", w: 51, d: 0, l: 59, pts: 153, weeks: 110, ppw: 1.39, status: "Active" }},
      {{ rank: 13, player: "Puru Lohiya", w: 50, d: 0, l: 60, pts: 150, weeks: 110, ppw: 1.36, status: "Active" }},
      {{ rank: 14, player: "Isaac Owen", w: 16, d: 0, l: 22, pts: 48, weeks: 38, ppw: 1.26, status: "Active" }},
      {{ rank: 15, player: "Arman", w: 13, d: 0, l: 25, pts: 39, weeks: 38, ppw: 1.03, status: "Relegated 24-25" }},
      {{ rank: 16, player: "Henry", w: 35, d: 0, l: 75, pts: 105, weeks: 110, ppw: 0.95, status: "Banished 25-26" }},
      {{ rank: 17, player: "Drew", w: 8, d: 0, l: 26, pts: 24, weeks: 34, ppw: 0.71, status: "Relegated 23-24" }},
      {{ rank: 18, player: "Rahul Mohankumar", w: 0, d: 0, l: 0, pts: 0, weeks: 0, ppw: 0.00, status: "Active (Debut)" }}
    ],

    prizeMoneyLeaderboard: [
      {{ manager: "Varun Kadikar", finishes: "7th, 5th, 1st (4.33)", money: 580, accolades: "24-25 Champions League, 25-26 League Title" }},
      {{ manager: "Shawn Hussain", finishes: "9th, 1st, 6th (5.33)", money: 365, accolades: "24-25 League Title, 25-26 Champions League" }},
      {{ manager: "Nilay Agarwalla", finishes: "3rd, 7th (5.00)", money: 215, accolades: "25-26 Lingineni Cup" }},
      {{ manager: "Ari Diddams", finishes: "4th, 7th, 2nd (4.33)", money: 180, accolades: "25-26 League Runner-Up" }},
      {{ manager: "Arnav Jain", finishes: "5th, 14th, 5th (8.00)", money: 175, accolades: "23-24 Playoff Champion" }},
      {{ manager: "Young Moon", finishes: "10th, 10th, 3rd (7.67)", money: 150, accolades: "25-26 3rd Place Podium" }},
      {{ manager: "Puru Lohiya", finishes: "11th, 9th, 8th (9.33)", money: 110, accolades: "24-25 Lingineni Cup" }},
      {{ manager: "Zach", finishes: "1st, 2nd, 13th (5.33)", money: 105, accolades: "23-24 League Title*, Relegated 25-26" }},
      {{ manager: "Suda", finishes: "6th, 4th, 11th (7.00)", money: 80, accolades: "Top 4 Finish (24-25)" }},
      {{ manager: "Joseph Lei", finishes: "3rd, 11th, 4th (6.00)", money: 40, accolades: "26-27 Champions League Qualifier" }},
      {{ manager: "Danny Najafian", finishes: "6th, 10th (8.00)", money: 20, accolades: "Top 6 Debut (24-25)" }},
      {{ manager: "Isaac Owen", finishes: "12th (12.00)", money: 20, accolades: "25-26 Survivor" }},
      {{ manager: "Subba Duvuuru", finishes: "8th, 9th (8.50)", money: 10, accolades: "25-26 Lingineni Cup Finalist" }},
      {{ manager: "Rahul Mohankumar", finishes: "Debut", money: 0, accolades: "2026-27 New Entrant" }},
      {{ manager: "Sean Bridges", finishes: "Debut", money: 0, accolades: "2026-27 New Entrant" }},
      {{ manager: "Henry", finishes: "8th, 13th, 14th (11.67)", money: 0, accolades: "Banished 25-26" }},
      {{ manager: "Arman", finishes: "12th (12.00)", money: 0, accolades: "Relegated 24-25" }},
      {{ manager: "Rithik", finishes: "2nd (2.00)", money: 0, accolades: "Relegated 23-24" }},
      {{ manager: "Drew", finishes: "12th (12.00)", money: 0, accolades: "Relegated 23-24" }}
    ],

    seasons: {{
      "2025-2026": {{
        summary: "The 2025-26 season saw a continuation of the previously established triple competition format. In miraculous fashion, the league and CL titles swapped hands between FC VAR and Smip Estonian, while Wallalujah wrote their names into the history books by securing the club’s maiden piece of silverware in just their second ever campaign. After much discourse, hdiamondpott did not heed the warnings brought forth to him at the beginning of the season by the Commission. Along with this, he refused the league punishment and was thus banished from both the competition and the community, likely and hopefully never to be heard from again.",
        standings: [
          {{ rank: 1, player: "Varun Kadikar", w: 27, d: 0, l: 11, pts: 81, weeks: 38, note: "Champion 🏆" }},
          {{ rank: 2, player: "Ari Diddams", w: 24, d: 1, l: 13, pts: 73, weeks: 38, note: "Runner-Up 🥈" }},
          {{ rank: 3, player: "Young Moon", w: 22, d: 0, l: 16, pts: 66, weeks: 38, note: "3rd Place 🥉" }},
          {{ rank: 4, player: "Joseph Lei", w: 21, d: 0, l: 17, pts: 63, weeks: 38, note: "CL Qualified" }},
          {{ rank: 5, player: "Arnav Jain", w: 21, d: 0, l: 17, pts: 63, weeks: 38, note: "CL Qualified" }},
          {{ rank: 6, player: "Shawn Hussain", w: 20, d: 0, l: 18, pts: 60, weeks: 38, note: "CL Champion" }},
          {{ rank: 7, player: "Nilay Agarwalla", w: 19, d: 0, l: 19, pts: 57, weeks: 38, note: "Lingineni Cup Champion" }},
          {{ rank: 8, player: "Subba Duvuuru", w: 19, d: 0, l: 19, pts: 57, weeks: 38, note: "Lingineni Finalist" }},
          {{ rank: 9, player: "Puru Lohiya", w: 19, d: 0, l: 19, pts: 57, weeks: 38, note: "" }},
          {{ rank: 10, player: "Danny Najafian", w: 17, d: 1, l: 20, pts: 52, weeks: 38, note: "" }},
          {{ rank: 11, player: "Suda", w: 17, d: 0, l: 21, pts: 51, weeks: 38, note: "" }},
          {{ rank: 12, player: "Isaac Owen", w: 16, d: 0, l: 22, pts: 48, weeks: 38, note: "" }},
          {{ rank: 13, player: "Zach", w: 15, d: 0, l: 23, pts: 45, weeks: 38, note: "Relegated" }},
          {{ rank: 14, player: "Henry", w: 8, d: 0, l: 30, pts: 24, weeks: 38, note: "Banished (Refused IHOP)" }}
        ],
        championsLeague: {{
          winner: "Shawn Hussain (Smip Estonian) 🏆",
          runnerUp: "Varun Kadikar (FC VAR)",
          groupStage: [
            {{ team: "Zach", w: 4, d: 0, l: 1, pts: 12 }},
            {{ team: "Nilay Agarwalla", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Shawn Hussain", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Varun Kadikar", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Danny Najafian", w: 2, d: 0, l: 3, pts: 6 }},
            {{ team: "Suda", w: 0, d: 0, l: 5, pts: 0 }}
          ],
          knockout: {{
            semiFinal1: "Varun Kadikar def. Zach",
            semiFinal2: "Shawn Hussain def. Nilay Agarwalla",
            final: "Shawn Hussain def. Varun Kadikar (Champions League Winner 🏆)"
          }}
        }},
        lingineniCup: {{
          winner: "Nilay Agarwalla (Wallalujah) 🏆",
          runnerUp: "Subba Duvuuru (sduvuuru)",
          finalMatch: "Nilay Agarwalla def. Subba Duvuuru in Final"
        }}
      }},

      "2024-2025": {{
        summary: "The 2024-2025 season saw the addition of four new teams and two new in-season tournaments. For the first time, silverware was given out for the league winner (Smip Estonian, Shawn Hussain), a Champions League winner (FC VAR, Varun Kadikar), and a Lingineni Cup winner (FC Purulona, Puru Lohiya). At the end of the season, Wes H00vlahan and their manager Arman Hussain were relegated from the league due to inactivity and offensive apathy after a lackluster debut season. After narrowly finishing below the disgraceful Henry Diamond-Pott due to fewer points, Arnav respectfully completed the IHOP punishment to secure his spot in the league for the next season.",
        standings: [
          {{ rank: 1, player: "Shawn Hussain", w: 27, d: 0, l: 11, pts: 81, weeks: 38, note: "Champion 🏆" }},
          {{ rank: 2, player: "Zach", w: 25, d: 1, l: 12, pts: 76, weeks: 38, note: "Runner-Up 🥈" }},
          {{ rank: 3, player: "Nilay Agarwalla", w: 25, d: 0, l: 13, pts: 75, weeks: 38, note: "3rd Place 🥉" }},
          {{ rank: 4, player: "Suda", w: 24, d: 0, l: 14, pts: 72, weeks: 38, note: "Top 4" }},
          {{ rank: 5, player: "Varun Kadikar", w: 23, d: 0, l: 15, pts: 69, weeks: 38, note: "CL Champion" }},
          {{ rank: 6, player: "Danny Najafian", w: 21, d: 0, l: 17, pts: 63, weeks: 38, note: "" }},
          {{ rank: 7, player: "Ari Diddams", w: 19, d: 1, l: 18, pts: 58, weeks: 38, note: "" }},
          {{ rank: 8, player: "Subba Duvuuru", w: 18, d: 1, l: 19, pts: 55, weeks: 38, note: "" }},
          {{ rank: 9, player: "Puru Lohiya", w: 18, d: 0, l: 20, pts: 54, weeks: 38, note: "Lingineni Cup Champion" }},
          {{ rank: 10, player: "Young Moon", w: 15, d: 1, l: 22, pts: 46, weeks: 38, note: "" }},
          {{ rank: 11, player: "Joseph Lei", w: 13, d: 2, l: 23, pts: 41, weeks: 38, note: "" }},
          {{ rank: 12, player: "Arman", w: 13, d: 0, l: 25, pts: 39, weeks: 38, note: "Relegated (Inactivity)" }},
          {{ rank: 13, player: "Henry", w: 11, d: 0, l: 27, pts: 33, weeks: 38, note: "" }},
          {{ rank: 14, player: "Arnav Jain", w: 11, d: 0, l: 27, pts: 33, weeks: 38, note: "Completed IHOP Challenge" }}
        ],
        championsLeague: {{
          winner: "Varun Kadikar (FC VAR) 🏆",
          runnerUp: "Joseph Lei (Traderjoe18)",
          groupStage: [
            {{ team: "Varun Kadikar", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Joseph Lei", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Ari Diddams", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Zach", w: 3, d: 0, l: 2, pts: 9 }},
            {{ team: "Suda", w: 2, d: 0, l: 3, pts: 6 }},
            {{ team: "Arnav Jain", w: 1, d: 0, l: 4, pts: 3 }}
          ],
          knockout: {{
            semiFinal1: "Varun Kadikar def. Zach",
            semiFinal2: "Joseph Lei def. Ari Diddams",
            final: "Varun Kadikar def. Joseph Lei (Champions League Winner 🏆)"
          }}
        }},
        lingineniCup: {{
          winner: "Puru Lohiya (FC Purulona) 🏆",
          runnerUp: "Zach",
          finalMatch: "Puru Lohiya def. Zach in Final"
        }}
      }},

      "2023-2024": {{
        summary: "The 2023-2024 inaugural edition was contested between 12 founding clubs, with Point Loma Parrots (Zach, regular season champion) and Arnie-senal (Arnav Jain, playoff champion) landing titles. Drewyomo FC were relegated following their last place finish and refusal to complete the league punishment. Linguini FC were relegated due to breaching FFP regulations.",
        standings: [
          {{ rank: 1, player: "Zach", w: 24, d: 0, l: 10, pts: 72, weeks: 34, note: "Regular Season Winner" }},
          {{ rank: 2, player: "Rithik", w: 21, d: 0, l: 13, pts: 63, weeks: 34, note: "Relegated" }},
          {{ rank: 3, player: "Joseph Lei", w: 20, d: 0, l: 14, pts: 60, weeks: 34, note: "" }},
          {{ rank: 4, player: "Arnav Jain", w: 19, d: 0, l: 15, pts: 57, weeks: 34, note: "Playoff Champion 🏆" }},
          {{ rank: 5, player: "Ari Diddams", w: 19, d: 0, l: 15, pts: 57, weeks: 34, note: "" }},
          {{ rank: 6, player: "Varun Kadikar", w: 17, d: 0, l: 17, pts: 51, weeks: 34, note: "" }},
          {{ rank: 7, player: "Suda", w: 17, d: 0, l: 17, pts: 51, weeks: 34, note: "" }},
          {{ rank: 8, player: "Henry", w: 16, d: 0, l: 18, pts: 48, weeks: 34, note: "" }},
          {{ rank: 9, player: "Shawn Hussain", w: 15, d: 0, l: 19, pts: 45, weeks: 34, note: "" }},
          {{ rank: 10, player: "Young Moon", w: 15, d: 0, l: 19, pts: 45, weeks: 34, note: "" }},
          {{ rank: 11, player: "Puru Lohiya", w: 13, d: 0, l: 21, pts: 39, weeks: 34, note: "" }},
          {{ rank: 12, player: "Drew", w: 8, d: 0, l: 26, pts: 24, weeks: 34, note: "Relegated (Refused IHOP)" }}
        ]
      }}
    }},

    wallOfShame: [
      {{
        name: "Henry (hdiamondpott)",
        season: "2025-2026",
        crime: "Refusal to complete the 24-hour IHOP Challenge after finishing dead-last (8-30), combined with repeated commissioner conduct violations.",
        fate: "Permanently banished from both the competition and the community, never to be heard from again."
      }},
      {{
        name: "Arman Hussain (Wes H00vlahan)",
        season: "2024-2025",
        crime: "Inactivity and offensive apathy after a lackluster debut campaign, abandoning active lineups mid-season.",
        fate: "Relegated and stripped of managerial license."
      }},
      {{
        name: "Drew (Drewyomo FC)",
        season: "2023-2024",
        crime: "Last place finish (8-26) followed by outright refusal to uphold the sacred IHOP pancake punishment.",
        fate: "Promptly relegated and blacklisted from league entry."
      }},
      {{
        name: "Linguini FC",
        season: "2023-2024",
        crime: "Severe breach of league Financial Fair Play (FFP) regulations and unauthorized transaction tampering.",
        fate: "Immediate structural expulsion."
      }}
    ]
  }}
}};
"""

    out_file_1 = os.path.join(BASE_DIR, "data.js")
    out_file_2 = os.path.join(PROJECT_ROOT, "soccer", "webpage", "data.js")

    with open(out_file_1, "w") as f:
        f.write(js_content)
    with open(out_file_2, "w") as f:
        f.write(js_content)

    print(f"Successfully synchronized real league data to {out_file_1} and {out_file_2}!")


if __name__ == "__main__":
    main()
