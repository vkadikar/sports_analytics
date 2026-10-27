---
name: gameweek_preview
description: A preview of one upcoming gameweek across the whole league: every fixture with a prediction, the match of the week, players to watch, and upset alerts. Use for "preview the week", "what's on this weekend", or "GW9 predictions".
---
# Gameweek preview

This is the league's weekly preview, written before a gameweek kicks off: every fixture gets a
prediction, and every number comes from the tools.

1. Work out the week. If the user named one, use it. Otherwise call `get_form_table` and use
   `weeks_played` + 1. If that week already has scores, it's under way: say so, and offer a
   recap of the last finished week instead.
2. Pull the data. These calls don't depend on each other, so make them together:
   - `get_matchups(week)` for the fixtures. Each game appears twice, once from each side, so
     count each game once.
   - `get_standings` for the table going in.
   - `get_form_table` for each team's season average, recent form, and `trend`.
   - `get_squad(limit=300)` with no team, for every rostered player's season points and points
     per game, tagged with the team that owns them.
3. For each fixture, call `get_head_to_head(team_a, team_b)` for earlier meetings this season.
   Make these calls together too.
4. Work out, from the data:
   - **Each fixture**: the favourite (higher average and better recent form; use the table to
     break a tie), a predicted score close to each side's recent averages, and each side's
     key player by points per game.
   - **Match of the week**: the fixture with the most riding on it, such as two top-four sides,
     a grudge rematch, or a scrap at the bottom.
   - **Upset alert**: the fixture where the underdog's form is closest to, or better than, the
     favourite's.
   - **High score race**: the two or three teams most likely to post the week's top score.
5. Write it up in this order, with headers:
   1. **Headline**: one line that sets up the week.
   2. **Match of the week**: the fixture, both sides' rank, points, and form, earlier meetings,
      the key players, and a predicted score.
   3. **The rest of the fixtures**: every other fixture, biggest first. For each: the fixture in
      bold with ranks (e.g. **FC VAR (1st) vs MOO FC (9th)**), two or three sentences on form
      and key players, then the predicted score.
   4. **Upset alert**: the fixture most likely to go against the table, and why.
   5. **High score watch**: who's in the running for the week's $10, with their averages.
   6. **Under pressure**: the manager at the bottom, or on the worst run, and what a loss means.

Aim for several hundred words. Commit to a pick in every fixture; don't hedge. Keep it in
character throughout.
