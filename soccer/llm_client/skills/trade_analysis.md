---
name: trade_analysis
description: Evaluating a trade between two teams: who wins a proposed or completed deal, whether it's fair, what to ask for, or finding a trade partner for a player.
---
# Trade analysis

1. Pin down the deal: which players go each way and which two teams are involved. If a side
   is missing, use `find_player` to find who owns the named players. If the user wants trade
   ideas rather than a verdict, skip to step 6.
2. Call `get_player_stats` once with every player in the deal, for the season, and again with
   `from_week` set three gameweeks before the latest played week, for current form.
3. For each player, work out:
   - **Output**: points per game, season and recent. Points per 90
     (`points / minutes * 90`) when minutes vary a lot.
   - **Repeatability**: the share of points from floor stats (tackles, interceptions, key
     passes, crosses, clearances, saves, shots on target) versus goals, assists, and clean
     sheets, from `points_breakdown`. A forward on a goal heater is a sell-high; a midfielder
     racking up tackles and key passes holds his value.
   - **Role**: minutes per game, and position eligibility (a dual-position player is worth
     more to a team that can use the flexibility).
4. Call `get_squad` for both teams. A trade can be lopsided on paper and still help both
   sides. Check:
   - who they'd start in the traded player's place, and that player's points per game; the
     real gain is the difference, not the traded player's total
   - whether either team is left short at a position
5. Call `get_standings` for context: a team fighting for the title should pay for points now;
   a team out of it can take the better long-term asset.
6. For trade ideas: find teams with surplus at the position the user can offer, and a need
   at the position the user wants, using `get_squad` (no `team_id`) by position. Suggest one
   or two deals that improve both lineups.
7. Answer with:
   - **The verdict first**: who wins the deal, and whether it's fair, lopsided, or daylight
     robbery.
   - **The numbers**: each player's season and recent points per game, minutes, and how
     repeatable their points are, in a short table.
   - **Lineup impact for both teams**: the net change in weekly points for each side.
   - **What to change**: the counter-offer or extra piece that would make it fair, or "take it
     and run".
