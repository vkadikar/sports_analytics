---
name: lineup_advice
description: Who to start and who to bench this gameweek: start/sit decisions, setting a lineup, or "who should I play at forward".
---
# Lineup advice

1. Work out whose lineup this is. If you don't know the user's team, ask.
2. Call `get_squad(team)` for the squad and current lineup status, and `get_player_stats` with
   every player the user is deciding between (or the whole squad's names if they want the full
   lineup), twice: once for the season and once with `from_week` set three gameweeks before
   the latest played week (from `get_form_table`'s `weeks_played`).
3. For each candidate, weigh:
   - **Recent form**: points per game over the last three weeks, against his season rate.
   - **Minutes**: a player with 0 minutes in a recent week may be injured, suspended, or
     dropped. Flag it rather than guessing why.
   - **The fixture** (`next_game`): home or away (an "@" means away), and how strong the
     opponent is. Defenders and goalkeepers gain most against weak attacks (clean sheets), and
     attackers against leaky defences. Use your Premier League knowledge for opponent strength
     and say it's your read, not league data.
   - **Floor vs. ceiling**: a player with lots of floor stats is the safe start in a close
     matchup; a goal-or-nothing player is the gamble when you need a big week.
4. If the user's matchup this week matters (they're the underdog, or it's close), call
   `get_head_to_head` to see the opponent's form. An underdog should take more risk.
5. Answer with:
   - **The lineup or the call**: start X over Y, in one line each.
   - **The reason**: one number for each (recent points per game, minutes, fixture).
   - **The risky call**: the one decision that could go either way, and which way you'd lean.
