---
name: gameweek_recap
description: A full write-up of one gameweek across the whole league: every result, the week's heroes and flops, bench blunders, table movement, and awards. Use for "recap the week", "what happened in GW8", or "weekly report".
---
# Gameweek recap

This is the league's weekly newsletter, so it should be long and thorough: every matchup gets
covered, and every number comes from the tools.

1. Work out the week. If the user named one, use it. Otherwise call `get_form_table` and use
   `weeks_played`, the latest played week. If the week they asked about has all scores at 0,
   it hasn't been played: say so, and offer a preview of the upcoming matchups instead.
2. Pull the data. These calls don't depend on each other, so make them together:
   - `get_matchups(week)` for the results. Each game appears twice, once from each side, so
     count each game once.
   - `get_gameweek_lineups(week)` for every team's lineup, the week's top performers, no-shows,
     and bench blunders.
   - `get_standings(through_week=week)` and `get_standings(through_week=week - 1)` for the
     table now and a week earlier, to show who moved. Skip the second call for week 1.
   - `get_form_table` for each team's season average and current form.
   - `get_weekly_scores` for every team's optimal-lineup score that week (`optimal_score`).
3. Work out, from the data:
   - **Each matchup**: winner, score, margin. Was it an upset (the lower-ranked team going in
     beat the higher one, using last week's table)? Who won it: the top scorer on each side.
     Who lost it: a no-show, a dud starter, or a bench blunder.
   - **Records**: the week's high and low scores, how each compares with the league's season
     average, and any season high or low.
   - **Team of the week**: the best starting XI from `top_performers`, as close to a real
     formation as the data allows (1 G, then the best mix of D, M, and F).
   - **Bench pain**: the biggest gap between a team's actual and optimal score, and the worst
     single bench blunder.
   - **Table movement**: who climbed, who dropped, and the top and bottom of the table.
   - **Form watch**: teams whose `trend` in the form table is well above or below zero.
4. Write it up in this order, with headers:
   1. **Headline**: one line that sums up the week.
   2. **The results**: every matchup, highest-scoring first. For each: the score in bold
      (e.g. **FC VAR 98.5 – 71.0 MOO FC**), then two or three sentences on how it was won and
      lost, naming players and their points.
   3. **Team of the week**: the XI, each with points and fantasy team, and the week's MVP.
   4. **Flops and blunders**: the worst no-shows and duds among starters, and the bench
      blunders, with points.
   5. **Bench pain**: who left the most on the bench, actual vs. optimal.
   6. **The table**: the top four and bottom three after the week, with movement arrows
      (▲2, ▼1) next to anyone who moved.
   7. **Awards**: four or five one-liners, such as Manager of the Week (high score), Wooden
      Spoon (low score), Robbery of the Week (luckiest win: the lowest winning score, or a win
      against a higher score elsewhere), Heartbreak (highest losing score), and Benchwarmer
      (biggest bench blunder).
   8. **Looking ahead**: one or two lines on next week's biggest matchup.

Aim for several hundred words, and more in a big week. Don't skip a matchup because it was
dull; give it a line and say it was dull. Keep it in character throughout.
