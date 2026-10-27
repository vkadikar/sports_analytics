---
name: waiver_analysis
description: Who to pick up and who to drop: waiver wire and free agent recommendations, the best available players at a position, trending pickups, or "should I add X".
---
# Waiver analysis

1. Work out whose team this is for. If the user named a team or said "my team" and you don't
   know which, ask. If the question is league-wide ("who's the best free agent?"), skip the
   team steps.
2. Call `get_squad(team)` for that team. Find the weak spots: the starters and bench players
   with the lowest points per game at each position, and anyone on injured reserve or not
   getting minutes (low `minutes` relative to `games_played`).
3. Search the market. Call `get_free_agents` twice for each position that needs help (or once
   per position for a general question):
   - season view: `sort_by="points_per_game"`, `min_games=3`
   - current form: `from_week` set three gameweeks before the latest played week (from
     `get_form_table`'s `weeks_played`), `sort_by="points"`
   A player near the top of both lists is a real pickup. Top of form only is a hot streak; top
   of season only may have lost his place.
4. Vet each candidate:
   - **Minutes**: points per game means nothing if he's playing 30 minutes. Check
     `minutes / games_played`; 70+ means a regular starter.
   - **Where the points come from** (`points_breakdown`): points from tackles, interceptions,
     key passes, crosses, clearances, and saves repeat week to week. Points from goals,
     assists, and clean sheets swing a lot. A player scoring mostly from floor stats is the
     safer add.
   - **Trend across Fantrax**: a high or rising `roster_pct_change` means other leagues are
     adding him. Get there first.
   - **Next fixture** (`next_game`) and **availability**: a free agent can be added now; a
     player on `waivers (<day>)` goes to the highest bid when he clears on that day.
5. Pair each add with a drop from step 2, at the same position where possible, and give the
   expected gain in points per game.
6. Answer with:
   - **The top pickup**: the player, club, position, points per game, minutes per game, and
     why he's the one, in two lines. Free agent or waivers.
   - **Two or three more options**, a line each.
   - **The drop**: who goes to make room, and the points per game you gain.
   - **One to avoid**: a popular name whose numbers are a mirage, if there is one.
