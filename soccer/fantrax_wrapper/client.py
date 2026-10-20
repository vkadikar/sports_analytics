"""
Main user-facing Fantrax API Client wrapper (FantraxClient).
"""

import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union
import pandas as pd
import numpy as np

from .session import FantraxSessionManager
from .rpc import FantraxRPCClient
from .scoring import FantasyScoringEngine
from .utils import add_season_year, parse_opponent, load_env_file
from .models import (
    LeagueInfo,
    StandingRow,
    WeeklyMatchup,
    TeamRoster,
    RosterRow,
    PlayerSummary,
    GameLogEntry,
)
from .analytics import (
    compute_optimal_lineup_score,
    calculate_manager_efficiency,
    calculate_median_standings,
    calculate_optimal_standings,
    compare_standings_vs_optimal,
    evaluate_waiver_candidates,
)


class FantraxClient:
    """High-level clean Python API wrapper for Fantrax Fantasy Premier League data."""

    def __init__(
        self,
        league_id: Optional[str] = None,
        cookie_path: Optional[str] = "fantraxloggedin.cookie",
        username: Optional[str] = None,
        password: Optional[str] = None,
        env_file_path: Optional[str] = None,
        session: Optional[Any] = None,
        scoring_engine: Optional[FantasyScoringEngine] = None,
        auto_login: bool = False,
    ):
        """Initialize FantraxClient.

        Args:
            league_id: Fantrax League ID string. If None, reads from FANTRAX_LEAGUE_ID env variable.
            cookie_path: Optional path to serialized authentication cookie file.
            username: Optional Fantrax account email/username. If None, reads from FANTRAX_USERNAME.
            password: Optional Fantrax account password. If None, reads from FANTRAX_PASSWORD.
            env_file_path: Optional filepath to .env file (defaults to soccer/config/.env).
            session: Optional pre-configured requests.Session instance.
            scoring_engine: Optional custom FantasyScoringEngine instance.
            auto_login: If True, attempts automated login if cookies are missing/expired and credentials exist.
        """
        # Load .env file automatically
        load_env_file(env_file_path)

        resolved_league_id = league_id or os.getenv("FANTRAX_LEAGUE_ID")
        if not resolved_league_id:
            raise ValueError(
                "league_id must be provided or set in environment variable FANTRAX_LEAGUE_ID (e.g. in soccer/config/.env)."
            )

        self.league_id = resolved_league_id
        self.session_manager = FantraxSessionManager(
            cookie_path=cookie_path,
            username=username,
            password=password,
            session=session,
            auto_login=auto_login,
        )
        self.rpc_client = FantraxRPCClient(league_id=self.league_id, session_manager=self.session_manager)
        self.scoring_engine = scoring_engine or FantasyScoringEngine()

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = True,
    ) -> bool:
        """Triggers automated login via headless browser using email & password.

        Args:
            username: Fantrax account email/username.
            password: Fantrax account password.
            headless: Whether to run Chrome in headless mode.

        Returns:
            True if login succeeded and cookies were saved; False otherwise.
        """
        return self.session_manager.login_with_credentials(
            username=username,
            password=password,
            headless=headless,
        )

    def _legacy_request(self, method_name: str, **kwargs) -> Dict[str, Any]:
        """Helper to invoke legacy Fantrax backend API endpoints."""
        data_payload = {"leagueId": self.league_id}
        for k, v in kwargs.items():
            if v is not None:
                data_payload[k] = str(v)

        message = {"method": method_name, "data": data_payload}
        res = self.rpc_client.send_rpc_request([message])
        responses = res.get("responses", [])
        if not responses:
            raise ValueError(f"No response returned for method {method_name}")
        return responses[0].get("data", {})

    def get_matchups(
        self,
        through_week: Optional[int] = None,
        only_completed: bool = False,
        optimal: bool = False,
        as_dataframe: bool = True
    ) -> Union[pd.DataFrame, List[WeeklyMatchup]]:
        """Fetches head-to-head weekly match schedule and scores.

        Args:
            through_week: Optional maximum matchweek integer to filter.
            only_completed: If True, only returns matchups with non-zero scores.
            optimal: If True, fetches optimal lineup scores for each matchup.
            as_dataframe: If True, returns pandas DataFrame; if False, returns list of WeeklyMatchup objects.

        Returns:
            DataFrame or list of WeeklyMatchup instances.
        """
        request_params = {"view": "SCHEDULE"}
        if optimal:
            request_params["optimal"] = True
        data = self._legacy_request("getStandings", **request_params)
        
        # Check scoringSystem.tableList first if non-empty, then fall back to top-level tableList
        table_list = data.get("scoringSystem", {}).get("tableList")
        if not table_list:
            table_list = data.get("tableList", [])

        matchups: List[WeeklyMatchup] = []
        rows_data = []

        matchup_id = 0
        for week_idx, week_data in enumerate(table_list):
            week_num = week_idx + 1
            if through_week is not None and week_num > through_week:
                continue

            for row in week_data.get("rows", []):
                cells = row.get("cells", [])
                if len(cells) < 4:
                    continue

                home_team = str(cells[0].get("content", ""))
                home_team_id = str(cells[0].get("teamId", "")).split("_")[0]
                home_score = float(cells[1].get("content", 0.0))
                away_team = str(cells[2].get("content", ""))
                away_team_id = str(cells[2].get("teamId", "")).split("_")[0]
                away_score = float(cells[3].get("content", 0.0))

                if only_completed and home_score == 0.0 and away_score == 0.0:
                    continue

                matchup = WeeklyMatchup(
                    week=week_num,
                    matchup_id=matchup_id,
                    home_team_id=home_team_id,
                    home_team_name=home_team,
                    home_score=home_score,
                    away_team_id=away_team_id,
                    away_team_name=away_team,
                    away_score=away_score,
                )
                matchups.append(matchup)

                rows_data.extend([
                    {
                        "week": week_num,
                        "team": home_team,
                        "team_id": home_team_id,
                        "score": home_score,
                        "opponent": away_team,
                        "opponent_score": away_score,
                        "matchupId": matchup_id,
                    },
                    {
                        "week": week_num,
                        "team": away_team,
                        "team_id": away_team_id,
                        "score": away_score,
                        "opponent": home_team,
                        "opponent_score": home_score,
                        "matchupId": matchup_id,
                    },
                ])
                matchup_id += 1

        if not as_dataframe:
            return matchups

        df = pd.DataFrame(rows_data)
        if not df.empty:
            df["result"] = np.where(
                df["score"] > df["opponent_score"], "W",
                np.where(df["score"] < df["opponent_score"], "L", "D")
            )
        return df

    def get_gameweek_dates(self) -> Dict[int, Dict[str, date]]:
        """Fetches the calendar date range of every scoring period (matchweek).

        Fantrax labels each schedule table with a sub-caption such as
        "(Fri Oct 16, 2026 - Thu Oct 22, 2026)"; both ends are inclusive.

        Returns:
            Mapping of week number to {"start": date, "end": date}. Weeks whose
            caption cannot be parsed are omitted.
        """
        data = self._legacy_request("getStandings", view="SCHEDULE")
        table_list = data.get("scoringSystem", {}).get("tableList") or data.get("tableList", [])

        dates: Dict[int, Dict[str, date]] = {}
        for week_idx, week_data in enumerate(table_list):
            caption = str(week_data.get("subCaption", "")).strip("() ")
            parts = [p.strip() for p in caption.split(" - ")]
            if len(parts) != 2:
                continue
            try:
                start, end = (datetime.strptime(p, "%a %b %d, %Y").date() for p in parts)
            except ValueError:
                continue
            dates[week_idx + 1] = {"start": start, "end": end}
        return dates

    def get_league_table(self, through_week: Optional[int] = None) -> pd.DataFrame:
        """Calculates current league standings table (Wins, Draws, Losses, Points, FPts For/Against).

        Args:
            through_week: Optional week limit.

        Returns:
            Sorted DataFrame of league standings.
        """
        matchups_df = self.get_matchups(through_week=through_week, as_dataframe=True)
        if matchups_df.empty:
            return pd.DataFrame()

        completed = matchups_df[matchups_df["score"] > 0]
        if completed.empty:
            completed = matchups_df

        standings = pd.DataFrame()
        standings["wins"] = completed.groupby("team")["result"].apply(lambda s: (s == "W").sum())
        standings["draws"] = completed.groupby("team")["result"].apply(lambda s: (s == "D").sum())
        standings["losses"] = completed.groupby("team")["result"].apply(lambda s: (s == "L").sum())
        standings["record"] = (
            standings["wins"].astype(str)
            + "-"
            + standings["draws"].astype(str)
            + "-"
            + standings["losses"].astype(str)
        )
        standings["points"] = standings["wins"] * 3 + standings["draws"]
        standings["fpts_for"] = completed.groupby("team")["score"].sum().round(2)
        standings["fpts_against"] = completed.groupby("team")["opponent_score"].sum().round(2)
        standings["avg_fpts_for"] = completed.groupby("team")["score"].mean().round(2)
        standings["avg_fpts_against"] = completed.groupby("team")["opponent_score"].mean().round(2)

        return standings.sort_values(["points", "fpts_for"], ascending=False)

    def get_team_roster(self, team_id: str, period: Optional[int] = 1) -> TeamRoster:
        """Fetches detailed team roster for a specific scoring period.

        Args:
            team_id: Fantrax team ID string.
            period: Optional scoring period / week number.

        Returns:
            TeamRoster object with structured starting XI and bench rows.
        """
        params = {"teamId": team_id, "timeStartType": "FROM_SEASON_START"}
        if period is not None:
            params["period"] = period
            # Without BY_PERIOD, Fantrax reports season-to-date points rather than this period's.
            params["timeframeTypeCode"] = "BY_PERIOD"

        data = self._legacy_request("getTeamRosterInfo", **params)
        tables = data.get("tables", [])
        rows = []
        for tbl in tables:
            rows.extend(tbl.get("rows", []))

        goalkeeper = None
        defenders = []
        midfielders = []
        forwards = []
        reserves = []
        injured_reserve = []

        for row in rows:
            scorer = row.get("scorer", {})
            if not scorer or not scorer.get("name"):
                continue

            player_name = scorer.get("name", "")
            player_id = scorer.get("scorerId", "")
            pos_short = scorer.get("posShortNames", "")
            status_id = str(row.get("statusId", "1"))

            cells = row.get("cells", [])
            pts_str = cells[1].get("content", "0") if len(cells) > 1 else "0"
            try:
                points = float(pts_str)
            except Exception:
                points = 0.0

            is_starter = (status_id == "1")
            is_reserve = (status_id == "2")
            is_injured_reserve = (status_id == "3")

            roster_row = RosterRow(
                player_id=player_id,
                player_name=player_name,
                position_short=pos_short,
                is_starter=is_starter,
                is_reserve=is_reserve,
                is_injured_reserve=is_injured_reserve,
                points=points,
            )

            if is_injured_reserve:
                injured_reserve.append(roster_row)
            elif is_reserve:
                reserves.append(roster_row)
            elif is_starter:
                if pos_short == "G":
                    goalkeeper = roster_row
                elif pos_short.startswith("D"):
                    defenders.append(roster_row)
                elif pos_short.startswith("M"):
                    midfielders.append(roster_row)
                elif pos_short.startswith("F"):
                    forwards.append(roster_row)
                else:
                    midfielders.append(roster_row)

        return TeamRoster(
            team_id=team_id,
            team_name="",
            week=period or 1,
            goalkeeper=goalkeeper,
            defenders=defenders,
            midfielders=midfielders,
            forwards=forwards,
            reserves=reserves,
            injured_reserve=injured_reserve,
        )

    # Fantrax lineup slot ids (row "posId") to position codes.
    SLOT_POSITIONS = {"704": "G", "703": "D", "702": "M", "701": "F"}
    _STATUS_NAMES = {"1": "starter", "2": "bench", "3": "injured_reserve"}

    def _roster_players(self, team_id: str, period: Optional[int], stats_type: str, timeframe: str) -> List[Dict[str, Any]]:
        """Players on a team's roster with one stats view's fantasy points, games played and minutes.

        stats_type "1" scores each player at their own position; "2" scores them in the lineup slot they
        filled for this fantasy team and only while active, which is what counts toward matchups.
        """
        params = {"teamId": team_id, "statsType": stats_type, "timeframeTypeCode": timeframe}
        if period is not None:
            params["period"] = period
        data = self._legacy_request("getTeamRosterInfo", **params)

        players = []
        for table in data.get("tables", []):
            header = [str(h.get("shortName", "")) for h in table.get("header", {}).get("cells", [])]
            col = {name: i for i, name in enumerate(header)}
            for row in table.get("rows", []):
                scorer = row.get("scorer") or {}
                if not scorer.get("name"):
                    continue  # empty lineup slot or a totals row
                cells = row.get("cells", [])

                def cell(name: str) -> str:
                    i = col.get(name)
                    return str(cells[i].get("content", "")) if i is not None and i < len(cells) else ""

                def number(name: str) -> float:
                    try:
                        return float(cell(name))
                    except ValueError:
                        return 0.0

                players.append({
                    "id": scorer.get("scorerId", ""),
                    "name": scorer["name"],
                    "positions": scorer.get("posShortNames", ""),
                    "slot": self.SLOT_POSITIONS.get(str(row.get("posId")), ""),
                    "club": scorer.get("teamShortName", ""),
                    "status": self._STATUS_NAMES.get(str(row.get("statusId")), "other"),
                    "game": " ".join(cell("Opp").replace("<br/>", " ").split()),
                    "points": number("FPts"),
                    "games_played": int(number("GP")),
                    "minutes": int(number("Min")),
                })
        return players

    def get_lineup(self, team_id: str, period: int) -> Dict[str, Any]:
        """A team's starting lineup and bench for one scoring period, with that period's fantasy points.

        Starters' points are what counted toward the matchup, so they sum to the team's score. Bench and
        injured-reserve points are what those players scored at their own position (not counted).

        Returns:
            {"team_id", "period", "total", "starters", "bench", "injured_reserve"}; each player is a dict
            with id, name, positions, slot, club, game, points, games_played, minutes.
        """
        counted = {p["id"]: p for p in self._roster_players(team_id, period, "2", "BY_PERIOD")}
        actual = self._roster_players(team_id, period, "1", "BY_PERIOD")

        order = {"G": 0, "D": 1, "M": 2, "F": 3}
        starters, bench, injured = [], [], []
        for player in actual:
            if player["status"] == "starter":
                player = {**player, "points": counted.get(player["id"], player)["points"]}
                starters.append(player)
            elif player["status"] == "injured_reserve":
                injured.append(player)
            else:
                bench.append(player)
        starters.sort(key=lambda p: order.get(p["slot"], 9))
        bench.sort(key=lambda p: order.get(p["positions"][:1], 9))

        return {
            "team_id": team_id,
            "period": period,
            "total": round(sum(p["points"] for p in starters), 2),
            "starters": starters,
            "bench": bench,
            "injured_reserve": injured,
        }

    def get_squad(self, team_id: str) -> List[Dict[str, Any]]:
        """A team's current players with their season-to-date fantasy points (scored at their own position).

        Each player dict also carries "status" ("starter", "bench" or "injured_reserve") for the current lineup.
        """
        order = {"starter": 0, "bench": 1, "injured_reserve": 2}
        positions = {"G": 0, "D": 1, "M": 2, "F": 3}
        squad = self._roster_players(team_id, None, "1", "YEAR_TO_DATE")
        return sorted(squad, key=lambda p: (order.get(p["status"], 9), positions.get((p["slot"] or p["positions"])[:1], 9)))

    def get_all_players(self, as_dataframe: bool = True) -> Union[pd.DataFrame, List[PlayerSummary]]:
        """Fetches all players in the league database across all paginated result pages.

        Args:
            as_dataframe: If True, returns DataFrame; if False, returns list of PlayerSummary.

        Returns:
            DataFrame or list of PlayerSummary instances.
        """
        first_page = self._legacy_request("getPlayerStats", statusOrTeamFilter="ALL", pageNumber=1)
        total_pages = first_page.get("paginatedResultSet", {}).get("totalNumPages", 1)

        players: List[PlayerSummary] = []
        rows_data = []

        for page in range(1, total_pages + 1):
            res = self._legacy_request("getPlayerStats", statusOrTeamFilter="ALL", pageNumber=str(page))
            for item in res.get("statsTable", []):
                scorer = item.get("scorer", {})
                cells = item.get("cells", [])

                scorer_id = str(scorer.get("scorerId", ""))
                name = str(scorer.get("name", ""))
                team_short = str(scorer.get("teamShortName", ""))
                team_name = str(scorer.get("teamName", ""))
                pos_short = str(scorer.get("posShortNames", ""))
                url_name = str(scorer.get("urlName", ""))

                next_match = cells[2].get("content", "") if len(cells) > 2 else ""
                fpts = float(cells[3].get("content", 0.0)) if len(cells) > 3 else 0.0
                fpts_per_game = float(cells[4].get("content", 0.0)) if len(cells) > 4 else 0.0

                opponent_short, is_home = parse_opponent(next_match.replace("<br/>", " "))

                player_summary = PlayerSummary(
                    scorer_id=scorer_id,
                    name=name,
                    team_short_name=team_short,
                    team_name=team_name,
                    position_short=pos_short,
                    next_match=next_match,
                    opponent_short_name=opponent_short,
                    fpts=fpts,
                    fpts_per_game=fpts_per_game,
                    url_name=url_name,
                )
                players.append(player_summary)

                row_dict = scorer.copy()
                row_dict.pop("icons", None)
                row_dict.update({
                    "scorerId": scorer_id,
                    "name": name,
                    "teamShortName": team_short,
                    "teamName": team_name,
                    "posShortNames": pos_short,
                    "next_match": next_match,
                    "opponentShortName": opponent_short,
                    "fpts": fpts,
                    "fpts_per_game": fpts_per_game,
                })
                rows_data.append(row_dict)

        if not as_dataframe:
            return players
        return pd.DataFrame(rows_data)

    def get_player_game_log(self, player_id: str, year: int = 2025) -> pd.DataFrame:
        """Fetches detailed game log statistics for a player in a given season.

        Args:
            player_id: Fantrax player/scorer ID.
            year: Calendar season year (e.g. 2025).

        Returns:
            DataFrame of player game logs with parsed dates, recalculated FPts, and aFPts.
        """
        raw_res = self.rpc_client.get_player_gamelog_rpc(player_id, year=year)
        sec = raw_res.get("responses", [{}])[0].get("data", {}).get("sectionContent", {}).get("GAME_LOG_FANTASY", {})

        tables = sec.get("tables", [])
        if not tables:
            return pd.DataFrame()

        rows = tables[0].get("rows", [])
        headers = [c.get("shortName", "") for c in tables[0].get("header", {}).get("cells", [])]

        parsed_rows = []
        for r in rows:
            cells = r.get("cells", [])
            row_dict = {}
            for idx, cell in enumerate(cells):
                if idx < len(headers):
                    col_name = headers[idx]
                    row_dict[col_name] = cell.get("content", "")
            parsed_rows.append(row_dict)

        df = pd.DataFrame(parsed_rows)
        if df.empty:
            return df

        df["player_id"] = player_id

        if "Date" in df.columns:
            df["Date_dt"] = df["Date"].apply(lambda d: add_season_year(d, year) if d else None)

        if "Opp" in df.columns:
            opp_parsed = df["Opp"].apply(parse_opponent)
            df["opp_clean"] = [p[0] for p in opp_parsed]
            df["is_home"] = [p[1] for p in opp_parsed]

        return df

    def get_player_news(self, player_id: str, url_name: str = "") -> str:
        """Fetches the latest news and analysis text for a player.

        Args:
            player_id: Fantrax player ID.
            url_name: Optional URL slug.

        Returns:
            Analysis text string.
        """
        res = self.rpc_client.get_player_overview_rpc(player_id, url_name=url_name)
        overview = res.get("responses", [{}])[0].get("data", {}).get("sectionContent", {}).get("OVERVIEW", {})
        latest_news = overview.get("latestNews", {})
        return latest_news.get("analysisText", "")

    def get_live_scoring(self, period: int = 1) -> pd.DataFrame:
        """Fetches live scoring and projected totals for all teams for a week.

        Args:
            period: Matchweek / scoring period number.

        Returns:
            DataFrame of live scores and projected fantasy points per player per team.
        """
        raw_res = self.rpc_client.get_live_scoring_rpc(period)
        all_teams_stats = (
            raw_res.get("responses", [{}])[0]
            .get("data", {})
            .get("statsPerTeam", {})
            .get("allTeamsStats", {})
        )

        rows = []
        for team_id, team_data in all_teams_stats.items():
            for status in ["ACTIVE", "BENCH"]:
                players_map = team_data.get(status, {}).get("projectedTotalsMap", {})
                for scorer_id, projection in players_map.items():
                    rows.append({
                        "teamId": team_id,
                        "status": status,
                        "scorerId": scorer_id,
                        "fantrax_projection": float(projection),
                        "week": period,
                    })

        return pd.DataFrame(rows)

    def get_raw_league_info(self, method: str = "getLeagueInfo", **kwargs) -> Dict[str, Any]:
        """Queries any raw Fantrax RPC endpoint method directly (e.g. getLeagueInfo, getLeagueRules, getDraftResults).

        Args:
            method: RPC method name string (default: 'getLeagueInfo').
            **kwargs: Additional parameters to pass in the RPC message payload.

        Returns:
            Raw response dict from Fantrax RPC endpoint.
        """
        return self._legacy_request(method, **kwargs)

    def get_optimal_lineup(self, team_id: str, period: int = 1) -> Dict[str, Any]:
        """Calculates the optimal Starting XI lineup and maximum possible score for a team in a given week.

        Args:
            team_id: Fantrax team ID string.
            period: Matchweek / scoring period number.

        Returns:
            Dict containing 'starters', 'bench', 'optimal_score', 'actual_score', and 'efficiency_pct'.
        """
        from fantrax_wrapper.analytics.manager_efficiency import compute_optimal_team_lineup

        roster = self.get_team_roster(team_id=team_id, period=period)

        roster_players = []
        all_roster_rows = ([roster.goalkeeper] if roster.goalkeeper else []) + roster.defenders + roster.midfielders + roster.forwards + roster.reserves + roster.injured_reserve

        for p in all_roster_rows:
            if not p or not p.player_name:
                continue
            roster_players.append({
                "player_id": p.player_id,
                "player_name": p.player_name,
                "position": p.position_short,
                "score": p.points,
                "was_starter": p.is_starter,
            })

        result = compute_optimal_team_lineup(roster_players)
        actual_score = round(sum(p["score"] for p in roster_players if p["was_starter"]), 2)
        optimal_score = result["optimal_score"]
        efficiency_pct = round((actual_score / optimal_score * 100.0), 2) if optimal_score > 0 else 100.0

        result["actual_score"] = actual_score
        result["efficiency_pct"] = efficiency_pct
        result["team_id"] = team_id
        result["week"] = period
        return result

    def get_league_manager_efficiency(self, through_week: Optional[int] = None) -> pd.DataFrame:
        """Calculates actual manager lineup efficiency and missed points for all teams across completed matchweeks.

        Fetches weekly matchups with actual scores and optimal scores,
        and aggregates actual scores vs optimal potential scores.

        Args:
            through_week: Optional maximum matchweek integer to evaluate.

        Returns:
            DataFrame summarizing average inefficiency, total missed points, avg actual score, and avg max score per team.
        """
        matchups = self.get_matchups(through_week=through_week, only_completed=True, as_dataframe=True)
        if matchups.empty:
            return pd.DataFrame(columns=["avg_inefficiency", "total_missed_points", "avg_actual_score", "avg_max_score"])

        opt_matchups = self.get_matchups(through_week=through_week, only_completed=True, optimal=True, as_dataframe=True)
        if not opt_matchups.empty:
            merged = pd.merge(
                matchups,
                opt_matchups[["week", "team", "score"]].rename(columns={"score": "max_points_for"}),
                on=["week", "team"],
                how="left"
            )
            merged["max_points_for"] = merged["max_points_for"].fillna(merged["score"])
        else:
            merged = matchups.copy()
            merged["max_points_for"] = merged["score"]

        return calculate_manager_efficiency(merged, only_completed=True)

    def get_optimal_standings(self, through_week: Optional[int] = None) -> pd.DataFrame:
        """Simulates league standings if every manager played their optimal lineup each matchweek.

        Fetches official optimal standings table from Fantrax (or computes from optimal schedule).

        Args:
            through_week: Optional maximum matchweek integer to evaluate.

        Returns:
            DataFrame containing simulated optimal standings table.
        """
        if through_week is None:
            data = self._legacy_request("getStandings", view="STANDINGS", optimal=True)
            table_list = data.get("tableList", [])
            if table_list:
                t0 = table_list[0]
                rows = []
                for r in t0.get("rows", []):
                    fixed = r.get("fixedCells", [])
                    cells = r.get("cells", [])
                    if len(fixed) >= 2 and len(cells) >= 9:
                        try:
                            rank = int(fixed[0].get("content", 0))
                        except Exception:
                            rank = 0
                        team = str(fixed[1].get("content", ""))
                        try:
                            wins = int(cells[0].get("content", 0))
                            draws = int(cells[1].get("content", 0))
                            losses = int(cells[2].get("content", 0))
                            points = int(cells[3].get("content", 0))
                            bench_lost = float(cells[5].get("content", 0.0))
                            efficiency = str(cells[6].get("content", "100%"))
                            fpts_for = float(cells[7].get("content", 0.0))
                            fpts_against = float(cells[8].get("content", 0.0))
                            streak = str(cells[9].get("content", "")) if len(cells) > 9 else ""
                        except Exception:
                            continue

                        rows.append({
                            "rank": rank,
                            "team": team,
                            "record": f"{wins}-{draws}-{losses}",
                            "points": points,
                            "fpts_for": fpts_for,
                            "fpts_against": fpts_against,
                            "bench_lost": bench_lost,
                            "efficiency": efficiency,
                            "streak": streak,
                            "wins": wins,
                            "draws": draws,
                            "losses": losses,
                        })

                if rows:
                    df = pd.DataFrame(rows).set_index("team")
                    return df

        opt_matchups = self.get_matchups(through_week=through_week, only_completed=True, optimal=True, as_dataframe=True)
        if opt_matchups.empty:
            return pd.DataFrame()

        opt_matchups["max_points_for"] = opt_matchups["score"]
        return calculate_optimal_standings(opt_matchups, only_completed=True)

    def get_draft_rankings(
        self,
        season_or_projection: str = "PROJECTION_0_926_SEASON",
        league_id: Optional[str] = None,
        sort_by_adp: bool = True,
        as_dataframe: bool = True,
    ) -> Union[pd.DataFrame, List[Dict[str, Any]]]:
        """Fetches draft rankings list including Average Draft Position (ADP), points, points per game, and percentage drafted.

        Season/Projection Identifier Notes:
            - 'PROJECTION_0_926_SEASON': Pre-season projection model for current 2026-27 season.
            - 'SEASON_926_YEAR_TO_DATE': 2026-27 season-to-date actuals (returns 0.0 pts prior to matchday 1).
            - 'SEASON_925_YEAR_TO_DATE' or 'PREVIOUS_SEASON': 2025-26 previous season actual stats (e.g. Haaland 509 pts, Fernandes 633.5 pts).

        Args:
            season_or_projection: Projection string identifier or alias (default: 'PROJECTION_0_926_SEASON').
                Supports aliases: 'PREVIOUS_SEASON', 'PREV_SEASON', 'YTD', 'PROJECTION'.
            league_id: Optional league ID override string. Defaults to configured client league_id.
            sort_by_adp: If True, sorts the returned draft list by Average Draft Position (ADP) ascending.
            as_dataframe: If True, returns a pandas DataFrame. Otherwise returns raw list of dicts.

        Returns:
            DataFrame or list of dictionaries containing draft rankings, ADP, points, and player projections.
        """
        # Map friendly season string aliases
        season_alias_map = {
            "PREVIOUS_SEASON": "SEASON_925_YEAR_TO_DATE",
            "PREV_SEASON": "SEASON_925_YEAR_TO_DATE",
            "LAST_SEASON": "SEASON_925_YEAR_TO_DATE",
            "SEASON_2025": "SEASON_925_YEAR_TO_DATE",
            "YTD": "SEASON_926_YEAR_TO_DATE",
            "PROJECTION": "PROJECTION_0_926_SEASON",
        }
        season_or_projection = season_alias_map.get(season_or_projection.upper(), season_or_projection)

        raw_res = self.rpc_client.get_draft_rankings_rpc(
            season_or_projection=season_or_projection,
            league_id=league_id,
        )

        responses = raw_res.get("responses", [])
        if not responses:
            return pd.DataFrame() if as_dataframe else []

        data = responses[0].get("data", {})
        full_stats = data.get("fullStats", [])

        parsed_players = []
        for rank_idx, item in enumerate(full_stats, start=1):
            scorer = item.get("scorer", {})
            pos_raw = scorer.get("posShortNames", "")
            pos_clean = pos_raw.replace("<b>", "").replace("</b>", "").strip()

            adp_val = float(item["adp"]) if item.get("adp") is not None else None
            pts_val = float(item.get("score", 0.0) or 0.0)

            player_row = {
                "rank": rank_idx,
                "player_id": scorer.get("scorerId", ""),
                "name": scorer.get("name", ""),
                "short_name": scorer.get("shortName", ""),
                "team": scorer.get("teamShortName", ""),
                "team_name": scorer.get("teamName", ""),
                "position": pos_clean,
                "adp": adp_val,
                "total_pts": pts_val,
                "projected_pts": pts_val,
                "pts_per_game": float(item.get("scorePerGame", 0.0) or 0.0),
                "percent_drafted": float(item.get("percentDrafted", 0.0) or 0.0),
            }
            parsed_players.append(player_row)

        if not parsed_players:
            # Fallback for active season when pre-draft ranking endpoint returns empty
            all_df = self.get_all_players(as_dataframe=True)
            if not all_df.empty:
                for idx, r in enumerate(all_df.to_dict(orient="records"), start=1):
                    parsed_players.append({
                        "rank": idx,
                        "player_id": str(r.get("scorerId", "")),
                        "name": str(r.get("name", "")),
                        "short_name": str(r.get("shortName", "")),
                        "team": str(r.get("teamShortName", "")),
                        "team_name": str(r.get("teamName", "")),
                        "position": str(r.get("posShortNames", "")),
                        "adp": float(idx),
                        "total_pts": float(r.get("fpts", 0.0) or 0.0),
                        "projected_pts": float(r.get("fpts", 0.0) or 0.0),
                        "pts_per_game": float(r.get("fpts_per_game", 0.0) or 0.0),
                        "percent_drafted": 100.0,
                    })

        if as_dataframe:
            if not parsed_players:
                return pd.DataFrame(columns=[
                    "rank", "player_id", "name", "short_name", "team", "team_name",
                    "position", "adp", "total_pts", "projected_pts", "pts_per_game", "percent_drafted"
                ])
            df = pd.DataFrame(parsed_players)
            if sort_by_adp and not df.empty:
                df = df.sort_values(by="adp", na_position="last").reset_index(drop=True)
                df["adp_rank"] = df.index + 1
            return df

        if sort_by_adp:
            parsed_players.sort(key=lambda x: (x["adp"] is None, x["adp"] if x["adp"] is not None else float("inf")))
            for idx, p in enumerate(parsed_players, start=1):
                p["adp_rank"] = idx

        return parsed_players
