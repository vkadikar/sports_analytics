"""
Low-level RPC layer for Fantrax web requests and /fxpa/req API protocol.
"""

from typing import Any, Dict, List, Optional
from requests import Session
from .session import FantraxSessionManager


FANTRAX_RPC_URL = "https://www.fantrax.com/fxpa/req"
DEFAULT_FANTRAX_VERSION = "190.0.0"


class FantraxRPCClient:
    """Handles direct Fantrax JSON-RPC payloads over the /fxpa/req endpoint."""

    def __init__(self, league_id: str, session_manager: FantraxSessionManager):
        """Initialize FantraxRPCClient.

        Args:
            league_id: Fantrax League ID string.
            session_manager: Configured FantraxSessionManager instance.
        """
        self.league_id = league_id
        self.session_manager = session_manager
        self.version = DEFAULT_FANTRAX_VERSION

    @property
    def session(self) -> Session:
        return self.session_manager.session

    def send_rpc_request(
        self,
        messages: List[Dict[str, Any]],
        ref_url: Optional[str] = None,
        uiv: int = 3,
        tz: str = "America/New_York",
        dt: int = 1,
        league_id: Optional[str] = None,
        retry_on_auth_fail: bool = True,
    ) -> Dict[str, Any]:
        """Sends a JSON-RPC request containing one or more messages to Fantrax.

        Automatically handles re-authentication and retries if session cookies have expired or client version is stale.

        Args:
            messages: List of message dicts, each with 'method' and 'data' keys.
            ref_url: Referrer URL header required by some endpoints.
            uiv: UI Version parameter.
            tz: Timezone parameter.
            dt: Data request flag (default 1, 0 for draft rankings).
            league_id: Optional league ID override. If None, uses configured self.league_id.
            retry_on_auth_fail: Whether to attempt automated login and retry if unauthenticated.

        Returns:
            Decoded JSON response dictionary from Fantrax.
        """
        target_league = league_id or self.league_id
        url = f"{FANTRAX_RPC_URL}?leagueId={target_league}"

        if not ref_url:
            ref_url = f"https://www.fantrax.com/fantasy/league/{target_league}/home"

        payload = {
            "msgs": messages,
            "uiv": uiv,
            "refUrl": ref_url,
            "dt": dt,
            "at": 0,
            "av": "0.0",
            "tz": tz,
            "v": self.version,
        }

        headers = {
            "User-Agent": self.session_manager.user_agent,
            "Content-Type": "application/json",
        }

        response = self.session.post(url, json=payload, headers=headers)
        response.raise_for_status()
        res_json = response.json()

        # Check for unauthenticated or page error responses
        page_error = res_json.get("pageError", {})
        error_code = page_error.get("code", "")
        has_empty_responses = not res_json.get("responses")

        # Handle STALE_CLIENT error code by updating version parameter and retrying
        if error_code == "STALE_CLIENT" and retry_on_auth_fail:
            self.version = "200.0.0"
            payload["v"] = self.version
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_json = response.json()
            page_error = res_json.get("pageError", {})
            error_code = page_error.get("code", "")
            has_empty_responses = not res_json.get("responses")

        if (error_code in ["WARNING_NOT_LOGGED_IN", "NOT_MEMBER_OF_LEAGUE"] or has_empty_responses):
            if retry_on_auth_fail and self.session_manager.auto_login and self.session_manager.username and self.session_manager.password:
                # Attempt automated login refresh once
                login_success = self.session_manager.login_with_credentials()
                if login_success:
                    # Retry request once with fresh session cookies
                    response = self.session.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    res_json = response.json()
                else:
                    # Disable auto_login for session to prevent repeated failed browser launches
                    self.session_manager.auto_login = False
            elif error_code in ["WARNING_NOT_LOGGED_IN", "NOT_MEMBER_OF_LEAGUE"]:
                print("Notice: Fantrax returned unauthenticated error. Session cookie may be expired. Run client.login() to authenticate.")

        return res_json

    def get_player_gamelog_rpc(self, player_id: str, year: int = 2025) -> Dict[str, Any]:
        """Fetches detailed game log fantasy stats for a player for a given season.

        Args:
            player_id: Fantrax scorer/player ID string.
            year: Calendar year of the season (e.g. 2025 for 2024-2025 season).

        Returns:
            Raw response dict containing GAME_LOG_FANTASY table data.
        """
        season_id = str(year - 1100)
        messages = [
            {
                "method": "getPlayerProfile",
                "data": {
                    "playerId": player_id,
                    "tab": "GAME_LOG_FANTASY",
                    "seasonId": season_id,
                },
            }
        ]
        ref_url = f"https://www.fantrax.com/fantasy/league/{self.league_id}/players;reload=1"
        return self.send_rpc_request(messages, ref_url=ref_url)

    def get_player_overview_rpc(self, player_id: str, url_name: str = "") -> Dict[str, Any]:
        """Fetches player overview information (next match fixture and latest news).

        Args:
            player_id: Fantrax player ID string.
            url_name: Optional URL slug for player.

        Returns:
            Raw response dict containing OVERVIEW table data and latest news.
        """
        messages = [
            {
                "method": "getPlayerProfile",
                "data": {
                    "playerId": player_id,
                },
            }
        ]
        ref_url = (
            f"https://www.fantrax.com/player/{player_id}/{self.league_id}/{url_name}"
            if url_name
            else f"https://www.fantrax.com/fantasy/league/{self.league_id}/players"
        )
        return self.send_rpc_request(messages, ref_url=ref_url)

    def get_live_scoring_rpc(self, period: int) -> Dict[str, Any]:
        """Fetches live scoring and projected totals for all teams in a scoring period.

        Args:
            period: Scoring period / matchweek number.

        Returns:
            Raw response dict with statsPerTeam live scores and projections.
        """
        messages = [
            {
                "method": "getLiveScoringStats",
                "data": {
                    "sppId": "-1",
                    "teamId": "ALL",
                    "period": period,
                    "viewType": "2",
                    "playerViewType": "2",
                    "newView": False,
                },
            },
            {
                "method": "getScoresSummaryData",
                "data": {},
            },
        ]
        ref_url = (
            f"https://www.fantrax.com/fantasy/league/{self.league_id}/livescoring;"
            f"period={period}?mobileMatchupView=true&layout=DETAILED&teamId=ALL&mode=fpts"
        )
        return self.send_rpc_request(messages, ref_url=ref_url)

    def get_draft_rankings_rpc(
        self,
        season_or_projection: str = "PROJECTION_0_926_SEASON",
        league_id: Optional[str] = None,
        dt: int = 0,
    ) -> Dict[str, Any]:
        """Fetches draft rankings and player projections for a given season or projection.

        Args:
            season_or_projection: Projection string identifier (e.g. 'PROJECTION_0_926_SEASON').
            league_id: Optional league ID override string.
            dt: Data request flag (0 for draft rankings).

        Returns:
            Raw response dict from Fantrax RPC containing fullStats and fantasyTeams.
        """
        target_league = league_id or self.league_id
        messages = [
            {
                "method": "getDraftRanks",
                "data": {
                    "seasonOrProjection": season_or_projection
                }
            },
            {
                "method": "getFantasyTeams",
                "data": {}
            }
        ]
        ref_url = (
            f"https://www.fantrax.com/fantasy/league/{target_league}/draft-ranking;"
            f"seasonOrProjection={season_or_projection}?sortKey=ADP&sortDir=-1"
        )
        return self.send_rpc_request(messages, ref_url=ref_url, dt=dt, league_id=target_league)
