"""
Fetches what the model needs: the player pool, each gameweek's stat lines, and the fixture list.

Stat lines come from the league's player stats listing, one date range per gameweek, which takes about
15 requests. Per-player game logs would be simpler but Fantrax rate limits player profiles after a
couple of hundred views. Finished gameweeks are saved in game_logs/<season>/ and only ever fetched once.

The FPL fixture feed only covers the current season. Past seasons' fixtures come from a few players'
game logs per club instead, which is what fetch_history builds. It only needs running once per season
(python3 -m fpts_model.train --fetch-history), and its files are committed, so the scheduled training
never has to fetch them. When a season ends, add its league to HISTORICAL_LEAGUES.
"""

import json
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

# Fantrax league for each past season, by the year it started
HISTORICAL_LEAGUES = {2025: "de19pr8smd5cytbm", 2024: "fc4ptfghlzanrcpt", 2023: "k6ryklcnlkicxhj9"}

PAUSE_BETWEEN_WEEKS_SECONDS = 5
PAUSE_BETWEEN_PROFILES_SECONDS = 4
RATE_LIMIT_WAIT_SECONDS = 120
MAX_RATE_LIMIT_WAITS = 8
GAMES_PER_CLUB = 38
MAX_PROFILES_PER_CLUB = 6
# Well under a matchday squad's worth of players means the listing came back incomplete
MIN_PLAYERS_PER_CLUB = 11


def game_log_path(season: int, week: int) -> Path:
    """Where a finished gameweek's stat lines are stored."""
    return GAME_LOGS_DIR / str(season) / f"gw{week:02d}.csv"


def latest_club(club: str) -> str:
    """A player's current club. Fantrax lists a player who moved during a season as 'CRY/MCI'."""
    return club.split("/")[-1]


def fetch_player_pool(client: FantraxClient) -> pd.DataFrame:
    """Every player in the league's pool, with the position their points are scored at by default."""
    pool = pd.DataFrame(client.get_player_stats(limit=5000))
    if pool.empty:
        raise RuntimeError("Fantrax returned no players. The login cookie has probably expired.")
    pool = pool[["id", "name", "positions", "scored_as", "club"]].assign(club=pool["club"].map(latest_club))
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
    drop_transfers: bool = False,
) -> pd.DataFrame:
    """One finished gameweek's stat lines, in the format clean_game_logs expects.

    A player is matched to the fixture of the club Fantrax lists them at now. For a gameweek that just
    finished that's their latest club. For a past season Fantrax can't say which of a transferred
    player's clubs a game was for, so drop_transfers leaves them out. A club with two games in a gameweek
    gets one combined stat line, against its first opponent.

    Raises:
        RuntimeError: The listing looks incomplete. Training on it would silently drop players.
    """
    dates = gw_dates[week]
    players = client.get_player_stats(start_date=dates["start"], end_date=dates["end"], limit=5000)
    played = [player for player in players if player["games_played"] > 0]

    this_week = fixtures[fixtures["week"] == week].sort_values("kickoff").drop_duplicates("club").set_index("club")
    counts = pd.Series([club for player in played for club in player["club"].split("/")]).value_counts() if played else pd.Series(dtype=int)
    thin = [club for club in this_week.index if counts.get(club, 0) < MIN_PLAYERS_PER_CLUB]
    if thin:
        raise RuntimeError(f"Fantrax returned too few players for GW {week} at {thin}. The login cookie may have expired.")
    unfinished = this_week.index[this_week["score"].isna()].tolist()
    if unfinished:
        raise RuntimeError(f"GW {week} has no final score yet for {unfinished}")

    rows = []
    for player in played:
        if drop_transfers and "/" in player["club"]:
            continue
        club = latest_club(player["club"])
        if club not in this_week.index:
            continue  # moved to a club with no fixture this gameweek
        fixture = this_week.loc[club]
        rows.append({
            "player_id": player["id"],
            "position": player["scored_as"],
            "Date": fixture["kickoff"].date().isoformat(),
            "Team": club,
            "Opp": fixture["opp"],
            "Score": fixture["score"],
            "Min": player["minutes"],
            **{stat: player["stats"].get(stat.upper()) for stat in TARGET_STATS},
        })
    return pd.DataFrame(rows)


def load_game_logs(
    client: FantraxClient,
    season: int,
    weeks: List[int],
    gw_dates: Dict[int, Dict[str, date]],
    fixtures: pd.DataFrame,
    drop_transfers: bool = False,
) -> pd.DataFrame:
    """Stat lines for finished gameweeks, fetching and saving any that aren't stored yet."""
    logs = []
    for week in weeks:
        path = game_log_path(season, week)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fetch_week_game_logs(client, week, gw_dates, fixtures, drop_transfers).to_csv(path, index=False)
            print(f"Fetched GW {week} stat lines", flush=True)
            time.sleep(PAUSE_BETWEEN_WEEKS_SECONDS)
        logs.append(pd.read_csv(path, keep_default_na=True, dtype={"player_id": str}, parse_dates=["Date"]))
    if not logs:  # training gameweek 1, with nothing played yet
        return pd.DataFrame({"player_id": pd.Series(dtype=str), "Team": pd.Series(dtype=str), "Date": pd.Series(dtype="datetime64[ns]")})
    return pd.concat(logs, ignore_index=True)


def _flip_result(score: str) -> str:
    """The same result from the other club's side: 'W 3-1' becomes 'L 1-3'."""
    letter, goals = score.split(" ")
    goals_for, goals_against = goals.split("-")
    return f"{ {'W': 'L', 'L': 'W'}.get(letter, letter) } {goals_against}-{goals_for}"


def _game_log_with_retries(client: FantraxClient, player_id: str, season: int) -> pd.DataFrame:
    """A player's game log. Fantrax answers with an empty one when it's rate limiting profile views."""
    for wait in range(MAX_RATE_LIMIT_WAITS + 1):
        log = client.get_player_game_log(player_id, year=season)
        if not log.empty:
            return log
        if wait < MAX_RATE_LIMIT_WAITS:
            print(f"No game log for {player_id}; waiting {RATE_LIMIT_WAIT_SECONDS}s in case of a rate limit", flush=True)
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
    raise RuntimeError(f"Fantrax kept returning no game log for {player_id} in {season}")


def fetch_historical_fixtures(
    client: FantraxClient,
    season: int,
    gw_dates: Dict[int, Dict[str, date]],
    players: List[dict],
) -> pd.DataFrame:
    """A past season's fixtures in fetch_fixtures' format, read from as few game logs as possible.

    Works through each club's players by minutes. A log covers its club and every opponent, so most of
    the league is known after a few clubs. Fixtures after a league's last gameweek are left out.
    """
    by_club: Dict[str, List[dict]] = {}
    for player in sorted(players, key=lambda p: p["minutes"], reverse=True):
        if "/" not in player["club"] and player["minutes"] > 0:
            by_club.setdefault(player["club"], []).append(player)

    games: Dict[tuple, dict] = {}
    views = 0
    for club, squad in sorted(by_club.items()):
        for player in squad[:MAX_PROFILES_PER_CLUB]:
            if sum(1 for key in games if key[0] == club) >= GAMES_PER_CLUB:
                break
            log = _game_log_with_retries(client, player["id"], season)
            views += 1
            time.sleep(PAUSE_BETWEEN_PROFILES_SECONDS)
            for row in log.to_dict("records"):
                if row["Team"] != club:
                    continue
                day = row["Date_dt"].date()
                opp, away = row["Opp"].removeprefix("@"), row["Opp"].startswith("@")
                games[(club, day)] = {"club": club, "day": day, "opp": row["Opp"], "score": row["Score"]}
                games[(opp, day)] = {"club": opp, "day": day, "opp": club if away else f"@{club}", "score": _flip_result(row["Score"])}
    print(f"{season}: read {views} game logs for {len(games) // 2} fixtures", flush=True)

    rows = [
        {"week": gameweek_of(game["day"], gw_dates), "kickoff": pd.Timestamp(game["day"]), "club": game["club"], "opp": game["opp"], "score": game["score"]}
        for game in games.values()
    ]
    return pd.DataFrame(rows).dropna(subset="week").astype({"week": int})


def fetch_history(client: FantraxClient, season: int) -> None:
    """Fetches and saves a past season's gameweek dates, fixtures and stat lines. Safe to re-run."""
    folder = GAME_LOGS_DIR / str(season)
    folder.mkdir(parents=True, exist_ok=True)
    gw_dates = client.get_gameweek_dates()
    if not gw_dates:
        raise RuntimeError(f"Fantrax returned no gameweek dates for {season}")
    (folder / "gameweeks.json").write_text(
        json.dumps({str(week): {k: v.isoformat() for k, v in dates.items()} for week, dates in gw_dates.items()}), encoding="utf-8"
    )

    fixtures_path = folder / "fixtures.csv"
    if not fixtures_path.exists():
        players = client.get_player_stats(limit=5000)
        fetch_historical_fixtures(client, season, gw_dates, players).to_csv(fixtures_path, index=False)
    fixtures = pd.read_csv(fixtures_path, parse_dates=["kickoff"])
    load_game_logs(client, season, sorted(gw_dates), gw_dates, fixtures, drop_transfers=True)


def load_history(season: int) -> tuple:
    """A past season's saved game logs and gameweek dates, or (empty frame, {}) if it hasn't been fetched."""
    folder = GAME_LOGS_DIR / str(season)
    paths = sorted(folder.glob("gw*.csv"))
    if not paths:
        return pd.DataFrame(), {}
    logs = pd.concat([pd.read_csv(path, dtype={"player_id": str}, parse_dates=["Date"]) for path in paths], ignore_index=True)
    raw = json.loads((folder / "gameweeks.json").read_text(encoding="utf-8"))
    gw_dates = {int(week): {k: date.fromisoformat(v) for k, v in dates.items()} for week, dates in raw.items()}
    return logs, gw_dates
