---
name: manager_roast
description: Roasting or slagging off a manager or team with their own numbers: "roast X", "how bad is X", "give Y some stick", "who's the worst manager".
---
# Manager roast

A roast lands when it's specific. Every insult should be pinned to a real number.

1. Pick the target. If the user asked for the league's worst manager, call `get_standings`
   and `get_efficiency` and choose the team with the worst combination of record and lineup
   management.
2. Gather the evidence. Make these calls together:
   - `get_team_results(team)`: record, form, their lowest score.
   - `get_efficiency`: points they've left on the bench.
   - `get_form_table`: luck (`actual_wins` vs. `expected_wins`), trend, and volatility.
   - `get_squad(team)`: their worst-performing starters and anyone rotting on injured reserve.
3. Find the best material:
   - their lowest score of the season and who beat them that week
   - the most points they left on the bench
   - a player they keep starting who keeps scoring nothing
   - a losing streak, or a run of bad form (`trend` well below zero)
   - if their record is better than it should be, call it out as pure luck; if worse, mock
     them for losing to worse teams anyway
4. Deliver it: four to six punchy lines, each with a number, building to the worst one. End
   with one backhanded compliment if there's anything good to say.

Keep the abuse on their football and fantasy decisions, as your persona says.
