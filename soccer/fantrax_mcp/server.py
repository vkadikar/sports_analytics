"""
MCP server exposing fantrax_wrapper as tools over the Model Context Protocol.

Each tool is a thin wrapper around a FantraxClient / FantasyScoringEngine
method, the same calls soccer/league_hub/app.py's REST API makes, so any MCP
client (Commish Bot, Claude Desktop, another agent) gets the league's live
data without talking to Fantrax directly.

Run standalone (stdio transport):
    cd soccer && python -m fantrax_mcp.server

Commish Bot launches this exact command as a subprocess; see
soccer/llm_client/mcp_client.py.
"""

from __future__ import annotations

import dataclasses
import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import numpy as np
from mcp.server.mcpserver import MCPServer

from fantrax_wrapper import (
    STAT_NAMES,
    FantraxClient,
    FantasyScoringEngine,
    calculate_median_standings,
    compute_optimal_lineup_score,
)

LEAGUE_ID = os.getenv("FANTRAX_LEAGUE_ID", "iku2an1nmryzcfa2")
COOKIE_PATH = os.getenv("FANTRAX_COOKIE_PATH") or os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
    "fantraxloggedin.cookie",
)

_scoring_engine = FantasyScoringEngine()


def _scoring_rules_text() -> str:
    """The league's scoring rules as a markdown table, sent to clients as the server's instructions."""
    positions = ["G", "D", "M", "F"]
    rows = []
    for stat, name in STAT_NAMES.items():
        points = [_scoring_engine.rules[pos].get(stat) for pos in positions]
        if any(p is not None for p in points):
            cells = " | ".join("-" if p is None else f"{p:+g}" for p in points)
            rows.append(f"| {name} (`{stat}`) | {cells} |")
    return (
        "## League scoring rules\n\n"
        "Fantasy points per stat, by position (G = goalkeeper, D = defender, M = midfielder, "
        "F = forward). A dash means the stat doesn't score at that position.\n\n"
        "| Stat | G | D | M | F |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "A player's season totals are scored at their primary position (`scored_as` in player "
        "data), even if they're eligible at two. In a matchup, a dual-position player is scored at "
        "the lineup slot they were started in. Clean sheets and goals conceded only count while the "
        "player is on the pitch."
    )


mcp = MCPServer("fantrax", instructions=_scoring_rules_text())


def _client() -> FantraxClient:
    return FantraxClient(league_id=LEAGUE_ID, cookie_path=COOKIE_PATH)


def _records(df) -> List[Dict[str, Any]]:
    """DataFrame -> JSON-friendly list of row dicts, index included as a column."""
    return df.reset_index().to_dict(orient="records")


def _team_ids(client: FantraxClient) -> Dict[str, str]:
    """{team name: Fantrax team ID} for every team in the league, read off gameweek 1's matchups."""
    matchups = client.get_matchups(through_week=1, as_dataframe=True)
    return dict(zip(matchups["team"], matchups["team_id"]))


def _fold(text: str) -> str:
    """Lowercase and strip accents, so "odegaard" matches "Ødegaard" and "nunez" matches "Núñez"."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _resolve_team(ids: Dict[str, str], team: str) -> str:
    """Team name (full or partial, any case) or team ID -> the exact team name. Raises a ValueError
    listing the league's teams when there's no single match, so the model can retry."""
    if team in ids.values():
        return next(name for name, tid in ids.items() if tid == team)
    query = _fold(team.strip())
    exact = [name for name in ids if _fold(name) == query]
    partial = [name for name in ids if query in _fold(name)]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0]
    problem = f"matches {len(matches)} teams ({', '.join(matches)})" if matches else "matches no team"
    raise ValueError(f'"{team}" {problem}. Teams: {", ".join(sorted(ids))}')


def _with_ppg(player: Dict[str, Any]) -> Dict[str, Any]:
    games = player.get("games_played") or 0
    return {**player, "points_per_game": round(player["points"] / games, 2) if games else None}


def _league_players(client: FantraxClient) -> List[Dict[str, Any]]:
    """Every rostered player in the league, each tagged with the fantasy team that owns them."""
    return [
        {**_with_ppg(player), "fantasy_team": team, "team_id": team_id}
        for team, team_id in _team_ids(client).items()
        for player in client.get_squad(team_id)
    ]


def _week_dates(client: FantraxClient, from_week: Optional[int], to_week: Optional[int]):
    """(start_date, end_date) covering gameweeks from_week..to_week inclusive, or (None, None) for the
    season to date. A missing bound is the first or last gameweek of the season."""
    if from_week is None and to_week is None:
        return None, None
    dates = client.get_gameweek_dates()
    first, last = from_week or min(dates), to_week or max(dates)
    if first not in dates or last not in dates:
        raise ValueError(f"No dates for gameweek {first if first not in dates else last}; weeks run 1-{max(dates)}.")
    return dates[first]["start"], dates[last]["end"]


def _with_breakdown(player: Dict[str, Any]) -> Dict[str, Any]:
    """Drops zero stats and adds points_breakdown: the fantasy points each stat earned at the player's
    scored_as position."""
    rules = _scoring_engine.rules.get(player["scored_as"], {})
    stats = {k: v for k, v in player["stats"].items() if v}
    breakdown = {k: round(v * rules[k], 2) for k, v in stats.items() if k in rules}
    return {**player, "stats": stats, "points_breakdown": breakdown}


def _results(matchups, team: str) -> List[Dict[str, Any]]:
    """One row per gameweek for a team. A week where both scores are still 0 hasn't been played,
    so its result is "upcoming" rather than the "D" Fantrax reports."""
    rows = []
    for row in matchups[matchups["team"] == team].sort_values("week").to_dict(orient="records"):
        played = row["score"] > 0 or row["opponent_score"] > 0
        rows.append({
            "week": int(row["week"]),
            "opponent": row["opponent"],
            "score": row["score"] if played else None,
            "opponent_score": row["opponent_score"] if played else None,
            "result": row["result"] if played else "upcoming",
        })
    return rows


@mcp.tool()
def get_standings(through_week: Optional[int] = None) -> Dict[str, Any]:
    """Live Fantrax league table: each team's name, team_id, points, W-D-L record, and points
    for/against, best first. Use the team_id with get_squad or get_team_roster.

    Args:
        through_week: Only count results through this gameweek (1-38). Omit for the season to date.
    """
    try:
        client = _client()
        ids = _team_ids(client)
        rows = _records(client.get_league_table(through_week=through_week))
        for row in rows:
            row["team_id"] = ids.get(row["team"])
        return {"standings": rows}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def find_player(name: str) -> Dict[str, Any]:
    """Finds which team in the league owns a player, searching every squad at once. Returns each
    match with the owning team, team_id, the player's club, position, lineup status, and
    season-to-date fantasy points. No matches means the player isn't rostered (a free agent).
    Use this for any question about a specific player instead of checking squads one by one.

    Args:
        name: Full or partial player name, e.g. "Haaland" or "Bruno". Case and accents don't matter.
    """
    try:
        query = _fold(name.strip())
        return {"query": name, "matches": [p for p in _league_players(_client()) if query in _fold(p["name"])]}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_efficiency(through_week: Optional[int] = None) -> Dict[str, Any]:
    """Manager lineup efficiency: each manager's actual points as a share of their best possible
    lineup's points, i.e. who optimizes their lineup and who leaves points on the bench.

    Args:
        through_week: Only count results through this gameweek (1-38). Omit for the season to date.
    """
    try:
        return {"efficiency": _records(_client().get_league_manager_efficiency(through_week=through_week))}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_optimal_standings(through_week: Optional[int] = None) -> Dict[str, Any]:
    """The league table as it would be if every manager had started their optimal lineup every week.

    Args:
        through_week: Only count results through this gameweek (1-38). Omit for the season to date.
    """
    try:
        return {"optimal_standings": _records(_client().get_optimal_standings(through_week=through_week))}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_median_standings(through_week: int = 38) -> Dict[str, Any]:
    """Standings if every manager played the league's median score each week instead of a real
    opponent, which strips out schedule luck.

    Args:
        through_week: Count results through this gameweek (1-38).
    """
    try:
        matchups = _client().get_matchups(through_week=through_week, as_dataframe=True)
        return {"median_standings": _records(calculate_median_standings(matchups))}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_matchups(week: int) -> Dict[str, Any]:
    """Head-to-head matchups and scores for one gameweek.

    Args:
        week: Gameweek number (1-38).
    """
    try:
        matchups = _client().get_matchups(through_week=week, as_dataframe=True)
        return {"week": week, "matchups": matchups[matchups["week"] == week].to_dict(orient="records")}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_team_results(team: str) -> Dict[str, Any]:
    """One team's whole season week by week (opponent, both scores, W/D/L, or "upcoming" for
    weeks not yet played), plus a summary: record, form over the last 5 played weeks, average,
    highest and lowest score.

    Args:
        team: Team name (full or partial, any case) or Fantrax team ID.
    """
    try:
        client = _client()
        name = _resolve_team(_team_ids(client), team)
        weeks = _results(client.get_matchups(through_week=38, as_dataframe=True), name)
        played = [w for w in weeks if w["result"] != "upcoming"]
        scores = [w["score"] for w in played]
        summary = {
            "record": "-".join(str(sum(w["result"] == r for w in played)) for r in "WDL"),
            "form_last_5": "".join(w["result"] for w in played[-5:]),
            "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
            "high_score": max(played, key=lambda w: w["score"]) if played else None,
            "low_score": min(played, key=lambda w: w["score"]) if played else None,
            "next_opponent": next((w for w in weeks if w["result"] == "upcoming"), None),
        }
        return {"team": name, "summary": summary, "weeks": weeks}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_head_to_head(team_a: str, team_b: str) -> Dict[str, Any]:
    """Every gameweek two teams meet this season: past results with both scores, and upcoming
    meetings. Also returns both teams' current standings rows, so you can compare their seasons.

    Args:
        team_a: Team name (full or partial, any case) or Fantrax team ID.
        team_b: The other team, same format.
    """
    try:
        client = _client()
        ids = _team_ids(client)
        a, b = _resolve_team(ids, team_a), _resolve_team(ids, team_b)
        if a == b:
            return {"error": f"Both names resolve to {a}; pick two different teams."}
        meetings = [w for w in _results(client.get_matchups(through_week=38, as_dataframe=True), a)
                    if w["opponent"] == b]
        table = _records(client.get_league_table())
        for rank, row in enumerate(table, start=1):
            row["rank"] = rank
        return {
            "team_a": a,
            "team_b": b,
            "meetings": meetings,  # scores and results are from team_a's side
            "standings": [row for row in table if row["team"] in (a, b)],
        }
    except Exception as e:
        return {"error": str(e)}


def _float_or_none(value) -> Optional[float]:
    return None if value is None or value != value else float(value)


def _played(matchups):
    """Rows for gameweeks that have been played: a week where every score is 0 hasn't started."""
    totals = matchups.groupby("week")["score"].transform("sum")
    return matchups[totals > 0]


@mcp.tool()
def get_weekly_scores() -> Dict[str, Any]:
    """Every team's score in every played gameweek, plus the opponent, the opponent's score, the
    result, and the team's optimal-lineup score that week. One compact grid for the whole
    season, meant for calculations (rolling averages, streaks, correlations) with run_python.
    """
    try:
        client = _client()
        matchups = _played(client.get_matchups(through_week=38, as_dataframe=True))
        optimal = client.get_matchups(through_week=38, optimal=True, as_dataframe=True)
        optimal = optimal.set_index(["week", "team"])["score"]
        rows = [
            {
                "week": int(r["week"]), "team": r["team"], "score": r["score"], "opponent": r["opponent"],
                "opponent_score": r["opponent_score"], "result": r["result"],
                "optimal_score": _float_or_none(optimal.get((r["week"], r["team"]))),
            }
            for r in matchups.sort_values(["week", "team"]).to_dict(orient="records")
        ]
        return {"weeks_played": int(matchups["week"].max()) if rows else 0, "rows": rows}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_form_table(window: int = 3) -> Dict[str, Any]:
    """Form and consistency stats for every team, computed from weekly scores: season average,
    rolling mean of the last `window` weeks, weighted moving average (recent weeks count more),
    exponentially weighted average, the trend (rolling mean minus season average), volatility
    (standard deviation), best and worst weeks, and the all-play record (how the team would do
    playing every other team every week, which strips out schedule luck). Sorted by
    exponentially weighted average, the best single measure of current strength.

    Args:
        window: How many recent gameweeks the rolling mean and weighted moving average cover.
    """
    try:
        matchups = _played(_client().get_matchups(through_week=38, as_dataframe=True))
        if matchups.empty:
            return {"error": "No gameweeks have been played yet."}
        grid = matchups.pivot_table(index="week", columns="team", values="score").sort_index()
        wins = matchups.assign(win=matchups["result"].eq("W")).groupby("team")["win"].sum()
        n = len(grid.columns) - 1
        rows = []
        for team in grid.columns:
            scores = grid[team].dropna()
            recent = scores.tail(window)
            weights = np.arange(1, len(recent) + 1)
            others = grid.drop(columns=team).loc[scores.index]
            ap_w = int((others.lt(scores, axis=0)).sum().sum())
            ap_d = int((others.eq(scores, axis=0)).sum().sum())
            ap_l = len(scores) * n - ap_w - ap_d
            ap_pct = (ap_w + ap_d / 2) / (len(scores) * n)
            avg = float(scores.mean())
            rows.append({
                "team": team,
                "weeks": len(scores),
                "avg": round(avg, 2),
                f"rolling_mean_{window}": round(float(recent.mean()), 2),
                f"wma_{window}": round(float((recent * weights).sum() / weights.sum()), 2),
                "ewma": round(float(scores.ewm(alpha=0.4).mean().iloc[-1]), 2),
                "trend": round(float(recent.mean()) - avg, 2),
                "std_dev": round(float(scores.std(ddof=0)), 2),
                "best_week": {"week": int(scores.idxmax()), "score": float(scores.max())},
                "worst_week": {"week": int(scores.idxmin()), "score": float(scores.min())},
                "all_play_record": f"{ap_w}-{ap_d}-{ap_l}",
                "all_play_win_pct": round(ap_pct, 3),
                "actual_wins": int(wins.get(team, 0)),
                "expected_wins": round(ap_pct * len(scores), 1),
            })
        rows.sort(key=lambda r: r["ewma"], reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["form_rank"] = rank
        return {
            "weeks_played": int(grid.index.max()),
            "window": window,
            "notes": "ewma uses alpha 0.4 (the latest week carries 40% of the weight). wma weights the "
                     "last `window` weeks 1, 2, ..., window. expected_wins = all_play_win_pct x weeks; "
                     "actual_wins well above it means a lucky schedule.",
            "teams": rows,
        }
    except Exception as e:
        return {"error": str(e)}


def _lineup_summary(team: str, lineup: Dict[str, Any]) -> Dict[str, Any]:
    starters, bench = lineup["starters"], lineup["bench"]
    keep = ("name", "slot", "positions", "club", "points", "minutes")
    # A bench player who outscored a starter they could have replaced (same position).
    blunders = []
    for b in bench:
        for s in starters:
            if s["slot"] in b["positions"].split(",") and b["points"] > s["points"]:
                blunders.append({"benched": b["name"], "benched_points": b["points"],
                                 "started": s["name"], "started_points": s["points"]})
                break
    return {
        "team": team,
        "score": lineup["total"],
        "starters": [{k: p[k] for k in keep} for p in starters],
        "bench": [{k: p[k] for k in keep} for p in bench],
        "bench_points": round(sum(p["points"] for p in bench), 2),
        "no_shows": [p["name"] for p in starters if p["minutes"] == 0],
        "bench_blunders": blunders,
    }


@mcp.tool()
def get_gameweek_lineups(week: int) -> Dict[str, Any]:
    """Every team's starting lineup and bench for one gameweek, with each player's points and
    minutes, in a single call. Per team it also lists starters who didn't play (no_shows) and
    bench_blunders (a benched player who outscored a starter at their position). League-wide it
    returns the week's top 15 performers among starters and the top 5 left on benches. Use for
    gameweek recaps, team of the week, and "who left points on the bench" questions.

    Args:
        week: Gameweek number (1-38).
    """
    try:
        ids = _team_ids(_client())

        def fetch(item):
            name, tid = item
            return _lineup_summary(name, _client().get_lineup(tid, week))

        with ThreadPoolExecutor(max_workers=4) as pool:
            teams = sorted(pool.map(fetch, ids.items()), key=lambda t: t["score"], reverse=True)
        tagged = lambda group: sorted(
            ({**p, "fantasy_team": t["team"]} for t in teams for p in t[group]),
            key=lambda p: p["points"], reverse=True,
        )
        return {
            "week": week,
            "top_performers": tagged("starters")[:15],
            "best_on_benches": tagged("bench")[:5],
            "teams": teams,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_team_roster(team_id: str, week: Optional[int] = None) -> Dict[str, Any]:
    """A manager's roster for a gameweek: starting goalkeeper, defenders, midfielders, forwards,
    bench, and injured reserve, each player with that gameweek's points.

    Args:
        team_id: Fantrax team ID (get_standings returns these).
        week: Gameweek number (1-38). Omit for the first scoring period.
    """
    try:
        return {"roster": dataclasses.asdict(_client().get_team_roster(team_id, period=week or 1))}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_squad(team_id: Optional[str] = None, position: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """Rostered players with season-to-date fantasy points, points per game, games played,
    minutes, real club, and lineup status.

    With team_id, returns that one team's squad. Without it, returns players from every team in
    the league in a single call, sorted by season points, each tagged with the fantasy team that
    owns them. Use that for league-wide questions ("best midfielders", "top scorers", "who has
    the most forwards") rather than calling this once per team. Free agents aren't included.

    Args:
        team_id: A Fantrax team ID or team name. Omit it for players from every team.
        position: Only players eligible at this position: "G", "D", "M", or "F". Dual-position
            players (e.g. "D,M") count for both.
        limit: Return at most this many players, highest season points first. Defaults to 25
            when team_id is omitted, and to the whole squad otherwise.
    """
    try:
        client = _client()
        if team_id:
            ids = _team_ids(client)
            team = _resolve_team(ids, team_id)
            players = [_with_ppg(p) for p in client.get_squad(ids[team])]
            result: Dict[str, Any] = {"team": team, "team_id": ids[team]}
        else:
            players = sorted(_league_players(client), key=lambda p: p["points"], reverse=True)
            limit = limit or 25
            result = {"scope": "all teams"}
        if position:
            players = [p for p in players if position.upper() in p["positions"].split(",")]
        if limit:
            players = sorted(players, key=lambda p: p["points"], reverse=True)[:limit]
        return {**result, "position": position, "players": players}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_free_agents(
    position: Optional[str] = None,
    sort_by: str = "points",
    min_games: int = 0,
    limit: int = 15,
    from_week: Optional[int] = None,
    to_week: Optional[int] = None,
) -> Dict[str, Any]:
    """Players nobody in the league owns (free agents, and players on waivers with the day they
    clear), best first, each with fantasy points, points per game, games, minutes, next real
    fixture, the share of Fantrax leagues that roster them (roster_pct) and its recent change
    (roster_pct_change, a sign of who's being picked up across Fantrax), their non-zero stats,
    and the points each stat earned. Use for pickup, waiver, and "who's out there" questions.

    Args:
        position: Only this position: "G", "D", "M", or "F". Omit for all positions.
        sort_by: "points" (total) or "points_per_game".
        min_games: Skip players with fewer games than this in the period. Use 3 or more with
            points_per_game so one-off big games don't top the list.
        limit: Return at most this many players (max 50).
        from_week: Only count gameweeks from this one on (1-38). Use it for current form, e.g.
            from_week 3 gameweeks back. Omit it and to_week for the season to date.
        to_week: Last gameweek to count (1-38). Set from_week and to_week equal for one gameweek.
    """
    try:
        client = _client()
        start, end = _week_dates(client, from_week, to_week)
        players = client.get_player_stats(
            position=position, available_only=True,
            sort_by="FPTS_PER_GAME" if sort_by == "points_per_game" else "SCORE",
            start_date=start, end_date=end,
        )
        players = [_with_breakdown(p) for p in players if p["games_played"] >= min_games][:min(limit, 50)]
        for p in players:
            del p["owner_team_id"]
        return {"from_week": from_week, "to_week": to_week, "position": position, "players": players}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_player_stats(
    names: List[str], from_week: Optional[int] = None, to_week: Optional[int] = None
) -> Dict[str, Any]:
    """Full stat lines for one or more players, owned or not: fantasy points, games, minutes, every
    non-zero stat (goals, assists, key passes, tackles, saves, ...), and points_breakdown, the
    fantasy points each stat earned under the league's scoring rules. Also returns the owning
    fantasy team (or free agent / waivers). Use this to explain where a player's points come
    from, or to compare players stat by stat. Pass several names in one call rather than calling
    once per player.

    Args:
        names: Player names, full or partial, e.g. ["Saka", "Bruno Fernandes"].
        from_week: Only count gameweeks from this one on (1-38). Omit it and to_week for the
            season to date.
        to_week: Last gameweek to count (1-38). Set from_week and to_week equal for one gameweek.
    """
    try:
        client = _client()
        start, end = _week_dates(client, from_week, to_week)
        owners = {tid: name for name, tid in _team_ids(client).items()}
        # Each search is two Fantrax requests; past a handful of names, one pass over the whole
        # player pool is faster.
        pool = client.get_player_stats(start_date=start, end_date=end, limit=2000) if len(names) > 6 else None
        results, not_found = {}, []
        for name in names:
            if pool is None:
                matches = client.get_player_stats(search=name.strip(), start_date=start, end_date=end, limit=10)
            else:
                query = _fold(name.strip())
                matches = [dict(p) for p in pool if query in _fold(p["name"])]
            if not matches:
                not_found.append(name)
            for p in matches:
                p = _with_breakdown(p)
                p["fantasy_team"] = owners.get(p.pop("owner_team_id"))
                results[p["id"]] = p
        return {"from_week": from_week, "to_week": to_week, "players": list(results.values()), "not_found": not_found}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def calculate_fantasy_score(stats: Dict[str, float], position: str) -> Dict[str, Any]:
    """Fantasy points (FPts) and adjusted fantasy points (aFPts) for a stat line under the league's
    scoring rules. Use for "what would X score" questions about a hypothetical stat line.

    Args:
        stats: Raw stat counts keyed by the stat codes in the scoring rules, e.g. {"G": 1, "SOT": 3}.
        position: Position code: "G", "D", "M", or "F".
    """
    try:
        position = position.upper()
        pos_rules = _scoring_engine.rules.get(position, {})
        return {
            "position": position,
            "fantasy_points": _scoring_engine.calculate_fantasy_score(stats, position),
            "adjusted_fantasy_points": _scoring_engine.calculate_adjusted_fantasy_score(stats, position),
            "scoring_breakdown": {k: stats[k] * pos_rules.get(k, 0) for k in stats if k in pos_rules},
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def compute_optimal_lineup(
    g_scores: List[float], d_scores: List[float], m_scores: List[float], f_scores: List[float]
) -> Dict[str, Any]:
    """The highest total a valid starting lineup could score from pools of player scores by position.

    Args:
        g_scores: Available goalkeeper scores.
        d_scores: Available defender scores.
        m_scores: Available midfielder scores.
        f_scores: Available forward scores.
    """
    try:
        return {"max_optimal_score": compute_optimal_lineup_score(
            [float(x) for x in g_scores], [float(x) for x in d_scores],
            [float(x) for x in m_scores], [float(x) for x in f_scores],
        )}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
