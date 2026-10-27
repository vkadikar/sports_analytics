---
name: matchup_analysis
description: Two specific teams against each other: previewing an upcoming matchup, breaking down a past one, or "who'd win between X and Y".
---
# Matchup analysis

1. Call `get_head_to_head(team_a, team_b)` with the two teams as the user named them. It gives
   every meeting this season (scores are from team_a's side) and both teams' standings rows with
   rank. If it says a name is ambiguous or unknown, pick from the team list it returns, or ask the
   user if you genuinely can't tell.
2. Call `get_team_results` for each team to get recent form (`form_last_5`), average score, and
   high and low scores.
3. Work out which matchup the user means:
   - **A past week** (they named one, or "last week"): call `get_matchups(week)` for the result
     and `get_team_roster` for both teams that week to name who won and lost it.
   - **Upcoming** (the default): use the next "upcoming" meeting from step 1. Call `get_squad`
     for both teams and pick out each side's top two or three scorers by season points.
4. Compare the two teams on:
   - points and rank
   - average score, and which team has been scoring more lately
   - form over the last 5 weeks
   - earlier meetings this season, if any
   - their key players
5. Answer in this order:
   - **The verdict first**: who wins or won, and by roughly how much.
   - **Two or three reasons**, each backed by a number.
   - **The X-factor**: the one player or trend that could flip it.

Keep it to a short paragraph or a tight list unless the user asks for a full breakdown. Commit
to a pick; don't hedge with "it could go either way".
