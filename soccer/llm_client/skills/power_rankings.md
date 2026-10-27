---
name: power_rankings
description: Ranking the whole league by true strength and current form rather than just the table: power rankings, "who's actually the best team", who's hot, who's overrated or underrated.
---
# Power rankings

1. Make these calls together:
   - `get_form_table(window=3)`: every team's season average, 3-week rolling mean, weighted
     moving average (`wma_3`), exponentially weighted average (`ewma`), trend, volatility
     (`std_dev`), all-play record, and expected vs. actual wins.
   - `get_standings`: the real table.
   - `get_efficiency`: lineup management.
2. Build a power score for each team that blends long-run strength with current form:
   - 50% `ewma` (current strength, recent weeks weighted most)
   - 30% season `avg` (the underlying level)
   - 20% `all_play_win_pct` scaled to points: multiply it by the league's average weekly score
   If you want the exact numbers, compute them with `run_python` instead of by hand. Rank by
   the power score. Use your judgement to nudge a team by a place where the data clearly
   supports it (e.g. a big injury or a lineup manager leaving 15 points a week on the bench),
   and say why.
3. Find the stories:
   - **Hottest and coldest**: the biggest positive and negative `trend` (rolling mean minus
     season average), and whose `wma_3` is well above their `ewma` (accelerating).
   - **Luck**: `actual_wins` minus `expected_wins`. More than 1 win above expected means a
     flattering record; more than 1 below means they've been robbed.
   - **Volatility**: the highest `std_dev` is the league's boom-or-bust side; the lowest is the
     most reliable.
   - **Overrated and underrated**: the biggest gaps between power rank and table position.
4. Answer with:
   - **A numbered list** of all teams. Each line: power rank, team, table position in
     brackets, movement vs. table (▲/▼), the key numbers (`ewma`, 3-week rolling mean, all-play
     record), and a few words of verdict. E.g. "1. MOO FC (2nd ▲1) · EWMA 104.0 · last 3: 98.2 ·
     all-play 68-1-35: in-form and it isn't a fluke".
   - **Hottest / coldest**, **luckiest / unluckiest**, **most volatile**, and **most overrated /
     underrated**: one line each, with the number that proves it.
   - A one-sentence note on method: power score = 50% EWMA, 30% season average, 20% all-play.

With 14 teams, the list is the answer. Keep each team's verdict short.
