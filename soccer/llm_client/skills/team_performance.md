---
name: team_performance
description: How one fantasy team or manager is doing overall: their season so far, form, whether they're lucky or good, strengths and weak spots.
---
# Team performance

1. Call `get_team_results(team)` for the record, the last-5-weeks form, the average, high, and
   low scores, and the next opponent.
2. Call `get_standings` to get the team's rank and their `team_id`.
3. Find out how much is skill and how much is luck. Call these and find the team in each:
   - `get_median_standings`: where they'd rank playing the league median every week. If they
     rank much higher here than in the real standings, they've been unlucky with opponents. If
     they rank much lower, they've been lucky.
   - `get_efficiency`: how many points they've left on their bench (`avg_inefficiency`,
     `total_missed_points`).
   - `get_optimal_standings`: where they'd rank with perfect lineups every week.
4. Call `get_squad(team_id)` and find:
   - the top three scorers, and what share of the team's points they produce
   - any weak spot: a position where their starters are scoring little, or a player sitting on
     injured reserve
5. Answer with:
   - **One line on their season**: record, rank, and form.
   - **Lucky or good**, comparing their real rank with their median rank, with both numbers.
   - **Lineup management**: are they leaving points on the bench?
   - **The engine room** (top scorers) and **the weak spot**.
   - **What's next**: the next opponent, and one thing the manager should change.

Be honest. If a team's record flatters them, say so.
