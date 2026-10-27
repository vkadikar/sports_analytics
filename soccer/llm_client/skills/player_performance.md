---
name: player_performance
description: How a specific player is doing: their fantasy output, who owns them, whether they're worth starting, trading for, or picking up.
---
# Player performance

1. Call `find_player(name)`. If it returns several matches, use the one that fits the user's
   wording, or list them and ask which one they mean. No matches means nobody owns the player:
   say they're a free agent and skip to step 3.
2. From the match, work out:
   - **Output**: season points, games played, points per game (`points / games_played`), and
     points per 90 minutes (`points / minutes * 90`). Points per 90 matters most for players who
     play limited minutes.
   - **Role**: their lineup `status` (starter, bench, or injured reserve), their real club, and
     their next real fixture (`game`).
3. Call `get_player_stats([name])` for where the points come from. Use `points_breakdown` to say
   what drives their score (goals, key passes, clean sheets, defensive work), and whether that
   source is repeatable or lucky. For current form, call it again with `from_week` set three
   gameweeks before the latest one played.
4. Call `get_squad(team_id)` for the owning team. This shows where the player ranks among
   their fantasy teammates by season points. Say whether they're carrying the side or a
   supporting piece, and what share of the team's top-end points they account for.
5. If the user is weighing a decision (start or sit, trade, pick up), compare against an
   alternative they named, or against players at the same position on the owner's squad. Pass
   both names to one `get_player_stats` call, compare points per game, and say which way you'd
   go. For a pickup, `get_free_agents(position)` shows the alternatives on the market.
6. Answer with:
   - **The headline number**: points per game, with total points in brackets.
   - **Who owns them**, and how important they are to that team.
   - **A one-line verdict**, e.g. "must-start", "sell high", or "bench until he's playing 90".

Don't invent stats the tools didn't return. `get_player_stats` has the scoring stats (goals,
assists, key passes, tackles, saves, and so on) but not xG, xA, or anything else outside the
scoring rules. If the user asks for those, say the league data doesn't have them.
