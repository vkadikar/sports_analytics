---
name: data_analysis
description: Custom number-crunching the other tools don't answer directly: streaks, correlations, rolling or weighted averages over any window, what-if scenarios, simulations, custom rankings or leaderboards, or "who has scored the most points since week X".
---
# Data analysis

Use `run_python` for anything that needs real arithmetic over more than a handful of
numbers. Don't do long calculations in your head.

1. Decide which data you need. Good sources for a script:
   - `get_weekly_scores`: every team's score, opponent, result, and optimal score, every week.
     The best starting point for anything about team scoring over time.
   - `get_squad()` (no `team_id`, with a large `limit`) or `get_squad(team_id)`: rostered
     players' season points.
   - `get_player_stats(names, from_week, to_week)` and `get_free_agents(...)`: stat lines
     and per-stat points.
   - `get_gameweek_lineups(week)`: who started and what they scored in one week.
2. Write one script that fetches the data with `tool()`, builds a DataFrame, does the
   calculation, and prints a compact result. For example:

   ```python
   df = pd.DataFrame(tool("get_weekly_scores")["rows"])
   grid = df.pivot(index="week", columns="team", values="score")
   last3 = grid.tail(3).mean().sort_values(ascending=False)
   print(last3.round(1).to_string())
   ```

   - Fetch with `tool()` inside the script rather than pasting tool results into the code.
   - Check a tool result for an `"error"` key before using it.
   - Print a few summary lines or a small table, not raw data. Round to one or two decimals.
   - To loop over weeks or teams, call `tool()` in a loop; the limit is 40 calls per script.
3. If the script fails, read the error, fix the script, and run it again once or twice. If it
   still fails, answer with what you have and say what you couldn't calculate.
4. Answer with the result first, then a line on how it was calculated (the window, the
   weights, what was counted) so the user can trust it. Don't paste the code unless the user
   asks for it.
