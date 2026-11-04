---
name: player_predictions
description: What the model predicted or predicts for a player or fantasy team in a gameweek: projected points, projected matchup winners, or how a prediction compared with what actually happened.
---
# Player predictions

1. Work out the gameweek. Use the one the user named. For "this week" or "next week" use
   `get_predictions` without a week, which returns the latest week the model has predicted, and
   check its `week` is the one they mean. Gameweek 1 has no predictions, because there was no
   earlier data to train on.
2. Call `get_predictions`:
   - **A player**: pass `player`. If several players match, use the one that fits the user's
     wording, or list them and ask. `fpts` is the prediction at their usual position; `by_position`
     has the alternatives for dual-position players. `stats` is the predicted stat line, so use it to
     say where the points are expected to come from.
   - **A fantasy team**: pass `team`. Use `predicted_total` for the starting XI and `predicted` per
     player. A `predicted` of null means the player has no fixture that week or no prediction.
   - **A matchup**: call it once per team and compare the two `predicted_total`s.
   - **The week's best**: pass neither, and use `top_predicted`.
3. For a gameweek that has been played, compare the prediction with the result. A team's call already
   includes actual `points` and `actual_total`; for a player, call
   `get_player_stats([name], from_week=week, to_week=week)`.
4. Answer with the predicted number first, then what drives it, then the actual result if the week has
   been played.

Be straight about what these numbers are. The model predicts a player's output assuming they feature,
from their rates this season and the opponent. It knows nothing about injuries, suspensions, rotation,
or who was named in the lineup, so check `minutes` or the player's status before leaning on a number,
and never present a prediction as a result. A big miss from a player who didn't play is the model's
blind spot, not a bad call on their form. Predictions are made once before the week and never change.
