---
name: player_predictions
description: What the model predicted or predicts for a player or fantasy team in a gameweek: projected points, projected matchup winners, or how a prediction compared with what actually happened.
---
# Player predictions

1. Work out the gameweek. Use the one the user named. For "this week" or "next week" use
   `get_predictions` without a week, which returns the latest week the model has predicted, and
   check its `week` is the one they mean.
2. Call `get_predictions`:
   - **A player**: pass `player`. If several players match, use the one that fits the user's
     wording, or list them and ask. `predicted_stats` says where the points are expected to come from.
   - **A fantasy team**: pass `team`. Use `predicted_total` for the starting XI and `predicted_points`
     per player. A null means the player has no fixture that week or no prediction.
   - **A matchup**: call it once per team and compare the two `predicted_total`s.
   - **The week's best**: pass neither, and use `top_predicted`.
   - **"What if they only play 30?"**: pass `minutes`.
3. Always say what minutes a number assumes (`predicted_at_minutes`). The model predicts output per
   minute and doesn't know who will play, so:
   - **Upcoming games** assume 90 minutes. That flatters squad players and impact subs, and a team's
     `predicted_total` assumes all eleven go the distance, so it runs high. Treat it as what a side
     could do, and use `get_squad` or recent minutes to judge who will actually play.
   - **Finished games** use the minutes actually played, which makes the prediction directly comparable
     with `actual_points`. It tests whether the model read the player's output, not whether it
     foresaw their minutes, so someone who didn't play predicts 0, and that's not a clever call.
4. Answer with the predicted number and its minutes first, then what drives it, then the actual result
   if the week has been played.

`basis` says what a number rests on. `player` is their own form. A player with no minutes this season
gets `position_vs_opponent` (what that position has produced against this opponent) or `position` (against
everyone, when that record is too thin). Say so when it applies: it describes the matchup, not the player.
In gameweek 1 nobody has minutes yet, so every player gets this, from last season's record.

Clean sheet points only count from 60 minutes, so the number jumps at that point for defenders and
goalkeepers. The model knows nothing about injuries, suspensions, or rotation. Never present a
prediction as a result. Predictions are made once before the week and never change.
