"""
Fetches what the model needs: the player pool, each gameweek's stat lines, and the fixture list.

Stat lines come from the league's player stats listing, one date range per gameweek, which takes about
15 requests. Per-player game logs would be simpler but Fantrax rate limits player profiles after a
couple of hundred views. Finished gameweeks are saved in game_logs/ and only ever fetched once.
"""

import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from fantrax_wrapper import FantraxClient

from .features import TARGET_STATS, gameweek_of

LEAGUE_TZ = ZoneInfo("America/New_York")
PL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"
PL_TEAMS_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
GAME_LOGS_DIR = Path(__file__).resolve().parent / "game_logs"

# FPL club codes that Fantrax spells differently
FPL_TO_FANTRAX_CLUB = {"BRE": "BRF", "NFO": "NOT"}

PAUSE_BETWEEN_WEEKS_SECONDS = 5
# Well under a matchday squad's worth of players means the listing came back incomplete
MIN_PLAYERS_PER_CLUB = 11


def game_log_path(week: int) -> Path:
    """Where a finished gameweek's stat lines are stored."""
    return GAME_LOGS_DIR / f"gw{week:02d}.csv"


def fetch_player_pool(client: FantraxClient) -> pd.DataFrame:
    """Every player in the league's pool, with the position their points are scored at by default."""
    pool = pd.DataFrame(client.get_player_stats(limit=5000))
    if pool.empty:
        raise RuntimeError("Fantrax returned no players. The login cookie has probably expired.")
    pool = pool[["id", "name", "positions", "scored_as", "club"]]
    return pool.rename(columns={"id": "player_id", "scored_as": "position"}).drop_duplicates("player_id")


def _result(goals_for, goals_against):
    """A club's result in game log format, such as 'W 4-0', or None if the game hasn't finished."""
    if goals_for is None or goals_against is None:
        return None
    letter = "W" if goals_for > goals_against else "L" if goals_for < goals_against else "T"
    return f"{letter} {goals_for}-{goals_against}"


def fetch_fixtures(gw_dates: Dict[int, Dict[str, date]]) -> pd.DataFrame:
    """Every Premier League fixture, as one row per club, assigned to its Fantrax gameweek."""
    headers = {"User-Agent": "Mozilla/5.0"}
    teams = requests.get(PL_TEAMS_URL, timeout=30, headers=headers)
    teams.raise_for_status()
    clubs = {t["id"]: FPL_TO_FANTRAX_CLUB.get(t["short_name"], t["short_name"]) for t in teams.json()["teams"]}
    res = requests.get(PL_FIXTURES_URL, timeout=30, headers=headers)
    res.raise_for_status()

    rows = []
    for fixture in res.json():
        if not fixture.get("kickoff_time"):
            continue  # postponed with no new date yet
        kickoff = datetime.fromisoformat(fixture["kickoff_time"].replace("Z", "+00:00")).astimezone(LEAGUE_TZ)
        week = gameweek_of(kickoff.date(), gw_dates)
        home, away = clubs[fixture["team_h"]], clubs[fixture["team_a"]]
        home_goals, away_goals = fixture.get("team_h_score"), fixture.get("team_a_score")
        rows.append({"week": week, "kickoff": kickoff, "club": home, "opp": away, "score": _result(home_goals, away_goals)})
        rows.append({"week": week, "kickoff": kickoff, "club": away, "opp": f"@{home}", "score": _result(away_goals, home_goals)})
    return pd.DataFrame(rows).dropna(subset="week").astype({"week": int})


def fetch_week_game_logs(
    client: FantraxClient,
    week: int,
    gw_dates: Dict[int, Dict[str, date]],
    fixtures: pd.DataFrame,
) -> pd.DataFrame:
    """One finished gameweek's stat lines, in the format clean_game_logs expects.

    A player is matched to the fixture of the club Fantrax lists them at now, so a player who has since
    transferred carries their new club's opponent for that week. A club with two games in a gameweek
    gets one combined stat line, against its first opponent.

    Raises:
        RuntimeError: The listing looks incomplete. Training on it would silently drop players.
    """
    dates = gw_dates[week]
    players = client.get_player_stats(start_date=dates["start"], end_date=dates["end"], limit=5000)
    played = [player for player in players if player["games_played"] > 0]

    this_week = fixtures[fixtures["week"] == week].sort_values("kickoff").drop_duplicates("club").set_index("club")
    counts = pd.Series([player["club"] for player in played]).value_counts() if played else pd.Series(dtype=int)
    thin = [club for club in this_week.index if counts.get(club, 0) < MIN_PLAYERS_PER_CLUB]
    if thin:
        raise RuntimeError(f"Fantrax returned too few players for GW {week} at {thin}. The login cookie may have expired.")
    unfinished = this_week.index[this_week["score"].isna()].tolist()
    if unfinished:
        raise RuntimeError(f"GW {week} has no final score yet for {unfinished}")

    rows = []
    for player in played:
        if player["club"] not in this_week.index:
            continue  # moved to a club with no fixture this gameweek
        fixture = this_week.loc[player["club"]]
        rows.append({
            "player_id": player["id"],
            "position": player["scored_as"],
            "Date": fixture["kickoff"].date().isoformat(),
            "Team": player["club"],
            "Opp": fixture["opp"],
            "Score": fixture["score"],
            "Min": player["minutes"],
            **{stat: player["stats"].get(stat.upper()) for stat in TARGET_STATS},
        })
    return pd.DataFrame(rows)


def load_game_logs(
    client: FantraxClient,
    weeks: List[int],
    gw_dates: Dict[int, Dict[str, date]],
    fixtures: pd.DataFrame,
) -> pd.DataFrame:
    """Stat lines for finished gameweeks, fetching and saving any that aren't stored yet."""
    GAME_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logs = []
    for week in weeks:
        path = game_log_path(week)
        if not path.exists():
            fetch_week_game_logs(client, week, gw_dates, fixtures).to_csv(path, index=False)
            print(f"Fetched GW {week} stat lines", flush=True)
            time.sleep(PAUSE_BETWEEN_WEEKS_SECONDS)
        logs.append(pd.read_csv(path, keep_default_na=True, dtype={"player_id": str}, parse_dates=["Date"]))
    return pd.concat(logs, ignore_index=True)
