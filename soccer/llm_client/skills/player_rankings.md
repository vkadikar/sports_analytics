---
name: player_rankings
description: Ranking players across the whole league: best players at a position, top scorers, most consistent, best per-game output, which teams have the best players.
---
# Player rankings

1. Call `get_squad` once without a `team_id`, which covers every team in one call. Pass
   `position` if the question is about one position ("G", "D", "M", or "F"), and a `limit` of
   about 15 so you have enough to rank from. Never call `get_squad` once per team for this.
2. Rank by what the question means:
   - **"Best" or "top"**: season points, with points per game as the tiebreaker.
   - **"Most consistent", "best per game", or "most efficient"**: points per game, counting
     only players with at least half the games played so far. A big week from a player who has
     played twice shouldn't top the list.
   - If the two orders disagree in an interesting way, e.g. a player low on total points but
     high per game, mention it.
3. Answer with:
   - **A numbered top 5** (or the number the user asked for). Each line gives the player,
     their real club, season points, points per game, and the fantasy team that owns them,
     e.g. "1. Pascal Gross (BHA): 124 pts, 17.7 per game, FC VAR".
   - **One or two lines of punditry**: who stands out, any team hoarding the best players, or a
     surprise name.
4. This only covers rostered players. If a free agent would make the list, or the user asks
   about all players, call `get_free_agents` with the same `position` and mention any free
   agent who'd crack the top 5.
