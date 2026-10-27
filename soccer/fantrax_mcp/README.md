# fantrax_mcp

An [MCP](https://modelcontextprotocol.io) server that exposes `fantrax_wrapper` as tools, so any
MCP client can query the league's live Fantrax data. Commish Bot (`soccer/llm_client`) is the
first client.

| Tool | Wraps |
|---|---|
| `get_standings(through_week?)` | `FantraxClient.get_league_table`, plus each team's `team_id` |
| `find_player(name)` | `get_squad` for every team, filtered by name (case- and accent-insensitive) |
| `get_efficiency(through_week?)` | `FantraxClient.get_league_manager_efficiency` |
| `get_optimal_standings(through_week?)` | `FantraxClient.get_optimal_standings` |
| `get_median_standings(through_week=38)` | `get_matchups` + `calculate_median_standings` |
| `get_matchups(week)` | `FantraxClient.get_matchups`, filtered to one gameweek |
| `get_team_results(team)` | One team's season week by week, plus record, form, high/low, next opponent |
| `get_head_to_head(team_a, team_b)` | Every meeting between two teams (past and upcoming), plus both standings rows |
| `get_team_roster(team_id, week?)` | `FantraxClient.get_team_roster` |
| `get_squad(team_id?, position?, limit?)` | `FantraxClient.get_squad` for one team, or for every team in one call when `team_id` is omitted (top 25 by points by default) |
| `get_free_agents(position?, sort_by?, min_games?, limit?, from_week?, to_week?)` | `FantraxClient.get_player_stats(available_only=True)`, with each player's stats and per-stat points |
| `get_player_stats(names, from_week?, to_week?)` | `FantraxClient.get_player_stats` per name, with per-stat points and the owning team |
| `get_weekly_scores()` | Every team's score, opponent, result, and optimal score for every played week |
| `get_form_table(window=3)` | Per team: season average, rolling mean, WMA, EWMA, trend, volatility, all-play record, expected wins |
| `get_gameweek_lineups(week)` | Every team's lineup for one week (`FantraxClient.get_lineup` per team), plus top performers, no-shows, bench blunders |
| `calculate_fantasy_score(stats, position)` | `FantasyScoringEngine` |
| `compute_optimal_lineup(g_scores, d_scores, m_scores, f_scores)` | `compute_optimal_lineup_score` |

`from_week` / `to_week` limit stats to an inclusive range of gameweeks. A missing bound runs to
the start or end of the season; omit both for the season to date.

The league's scoring rules, generated from `FantasyScoringEngine`, are sent as the server's MCP
`instructions` when a client connects. Commish Bot appends them to its system prompt.

Every tool returns a JSON object, or `{"error": "..."}` when the call fails, so a client never
receives an exception. Tools that take a `team` accept a full or partial team name (any case)
or a team ID. An ambiguous name returns an error listing the league's teams, so the model can
retry with the right one.

## Running it

It uses the stdio transport, and it reads the league ID and Fantrax cookie the same way
`league_hub/app.py` does (`FANTRAX_LEAGUE_ID`, `FANTRAX_COOKIE_PATH`, or
`fantraxloggedin.cookie` at the repo root).

```bash
cd soccer && ../.venv/bin/python -m fantrax_mcp.server
```

You don't normally run it yourself: Commish Bot starts it as a subprocess the first time it
needs a tool (`llm_client/mcp_client.py`) and keeps that one process for the server's lifetime.

To use it from another MCP client such as Claude Desktop, register the same command with
`cwd` set to the `soccer/` directory.

## Adding a tool

Add a function decorated with `@mcp.tool()` to `server.py`, with type hints and a docstring.
The docstring and `Args:` section become the description the model sees. Commish Bot picks up
new tools on its next restart.
