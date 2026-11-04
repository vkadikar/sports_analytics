# fpts_model

Predicts each player's fantasy output for a gameweek. There are 23 random forests, one per scored stat.
Each forest predicts how much of its stat a player produces per minute, so a prediction can be scaled to
any number of minutes. Clean sheets are the exception (see [Targets](#targets-and-weights)).

This page documents every feature and how it's built. The code is in [features.py](./features.py).

## How a feature row is built

A row is one player in one game. Rows come from the stat lines in `game_logs/<season>/gw<NN>.csv`, plus a
blank row for each player's fixture in the gameweek being predicted.

**The main rule: features are point in time.** A row in gameweek N only uses games from before gameweek N.
So the result of a game can never reach that game's own features, or any earlier game's.
`test_every_feature_ignores_its_own_and_later_gameweeks` enforces this.

**Each season is built separately.** `build_features` runs once per season, so form and standings start from
zero each year. Past seasons contribute training rows, not form carried into the new season.

**Gameweeks are Fantrax's.** A game's gameweek comes from its date and Fantrax's date ranges, not from a count
of each club's games.

## Features at a glance

Each forest sees the 9 context features. Forests for the 18 rolling stats also see 4 rate features for their
own stat, so the goals forest can't see shots on target, for example.

| Feature | Meaning | Unit |
|---|---|---|
| `player_id` | The player | integer code |
| `team` | The player's club | integer code |
| `opp` | The opponent | integer code |
| `position` | Position the player is scored at | integer code |
| `is_away` | Whether the game is away | 0 or 1 |
| `team_week_standing` | Club's league position going into the gameweek | 1 = top |
| `team_week_standing_opp` | Opponent's league position going into the gameweek | 1 = top |
| `has_season_form` | Whether the player has appeared earlier this season | 0 or 1 |
| `has_opponent_record` | Whether this position has faced this opponent earlier this season | 0 or 1 |
| `{stat}_per_min_last_appearance` | Player's rate in their previous appearance | per minute |
| `{stat}_per_min_season` | Player's rate this season so far | per minute |
| `positional_avg_{stat}_per_min_last_appearance` | Rolling, time-weighted average of `{stat}_per_min_last_appearance` for this position against this opponent | per minute |
| `positional_avg_{stat}_per_min_season` | Rolling, time-weighted average of `{stat}_per_min_season` for this position against this opponent | per minute |

## The stats

| Rolling stats (13 features) | |
|---|---|
| `g` Goals | `dis` Dispossessed |
| `kp` Key passes | `acnc` Accurate crosses (not corners) |
| `at` Assists | `clr` Effective clearances |
| `sot` Shots on target | `aer` Aerials won |
| `tkw` Tackles won | `gao` Goals conceded on the pitch |
| `int` Interceptions | `cs` Clean sheets |
| `cos` Successful dribbles | `sv` Saves |
| `bs` Blocked shots | `pks` Penalty kick saves |
| `hcs` High claims | `sm` Smothers |

**Context-only stats (9 features):** `yc` Yellow cards, `rc` Red cards, `pkm` Penalties missed, `pkd` Penalties
drawn, `og` Own goals. These have no rate features, a choice inherited from the original notebook.

`min` (minutes) and the raw stat values are inputs and targets, never features.

## Context features

### `player_id`, `team`, `opp`, `position`

**Source:** `player_id` is the Fantrax ID, which stays the same across seasons. `team` and `opp` are Fantrax
club codes. `position` is Fantrax's `scored_as` value (G, D, M or F).

**Construction:** `FptsModel._encode` swaps each value for an integer, numbered by first appearance in the
feature table. The list is saved in the model's `encoders`.

**Note:** the integers have no meaning, but a forest treats them as ordered. A split like `player_id <= 412`
just groups whichever players happen to fall on each side.

### `is_away`

**Source:** the opponent field. `@NOT` means away at Nottingham Forest, and `NOT` means at home.

**Construction:** 1 if the field starts with `@`, otherwise 0. The `@` is then removed to give `opp`.

### `team_week_standing`, `team_week_standing_opp`

**Source:** final scores of games in **earlier gameweeks of the same season**. Each club's result is taken
once per game.

**Construction** (`_league_standings`), for each gameweek:

1. Add up each club's table points (3 for a win, 1 for a tie), goals for and goals against.
2. Sort by points, then goal difference, then goals for, then fewest goals against, then club code.
3. Rank from 1. The opponent's rank is looked up the same way.

**Notes:** every club is level before the first game of a season, so gameweek 1 standings are just alphabetical
and mean nothing. Past seasons are missing a few fixtures (1 to 3 of 380), which slightly affects their tables.

### `has_season_form`, `has_opponent_record`

**Why:** undefined rates and averages are filled with 0, which looks the same as a real rate of 0. These flags
let the forests tell "no data yet" from "produced nothing".

**Construction:** `has_season_form` is 1 if the player has a played game earlier this season.
`has_opponent_record` is 1 if any player at this position has faced this opponent in an earlier gameweek this
season. It can be 1 while the averages are still 0, because trimming can empty an average built from a few games.

## Rate features

These are built in `_add_rolling_stats`. For a row, each player's games so far this season are in date order,
and only appearances count. A gameweek where the player didn't feature has no row.

### `{stat}_per_min_last_appearance`

The player's stat divided by their minutes in their **previous appearance**, which may be weeks ago if they've
missed games.

### `{stat}_per_min_season`

The player's total stat divided by their total minutes, across all their appearances this season before this
game.

### Undefined rates

A player's first appearance of a season has no earlier minutes, so both rates are undefined. They're filled
with 0 at the end of `build_features`, and `has_season_form` marks those rows.

### A second fixture in the same gameweek

When a player has two unplayed fixtures in the predicted gameweek, the second copies the first's rates. Otherwise
it would treat the first, unplayed fixture as a 0-minute game.

## Positional average features

### `positional_avg_{stat}_per_min_last_appearance`, `positional_avg_{stat}_per_min_season`

These are rolling, time-weighted averages. Rolling means each gameweek's value is recalculated from every earlier
gameweek of the season. Time-weighted means recent games count for more.

**Construction** (`_add_positional_averages`), for each season, opponent, position and gameweek:

1. Take all rows for that position against that opponent in **earlier gameweeks**.
2. For each rate column, keep values between the 5th and 95th percentiles, inclusive. Undefined rates are ignored.
3. Give each remaining row a weight of `0.5 ^ (days before this gameweek / 30)`, so its weight halves every 30 days
   (`OPPONENT_AVERAGE_HALF_LIFE_DAYS`).
4. Take the weighted average: the sum of value × weight, divided by the sum of weights for rows with a value.

For example, with a 30-day half-life, a game from 30 days ago counts half as much as one from today, and a game from
60 days ago counts a quarter as much.

The result is undefined, and filled with 0, the first time a position meets an opponent in a season. It's also
undefined when trimming removes every value: with exactly two values, both fall outside the percentiles.

**Why the half-life is 30 days:** in the backtest, 14 to 120 days scored almost the same, with shorter half-lives
slightly ahead, so this value isn't sensitive. Weighting gave a small gain over no weighting.

**Trimming on small samples:** trimming only at 20+ values looks more sensible, but it made the model measurably
worse (error 4.36 vs 4.32), so short samples are trimmed too. Cameos can give huge rates, which is the likely reason,
though that isn't proven.

**Known limitation:** this doesn't measure what the opponent concedes. Each value being averaged is a player's
rate **before** they faced this opponent, so it describes the form of the players who've met this opponent, not
how they did against it.

**Tried and rejected:** `opp_conceded_{stat}_per_min`, the position's actual output against the opponent, weighted
the same way. It made the model worse, both alongside these averages (error 4.34 vs 4.32) and replacing them
(4.35). That's surprising, and it may just be too noisy with so few games per opponent. The
[no-minutes rule](#players-with-no-minutes-this-season) does use actual output, because it needs a number from the
position alone.

## Worked example

Erling Haaland (MCI, forward) away at Nottingham Forest in gameweek 10, for the goals forest. His 9 appearances
before that had 9 goals in 799 minutes, and the last was 0 goals in 90 minutes against Brighton.

| Feature | Value | How |
|---|---|---|
| `team`, `opp`, `position` | MCI, NOT, F | Before encoding |
| `is_away` | 1 | Opponent field is `@NOT` |
| `has_season_form` | 1 | 9 earlier appearances |
| `has_opponent_record` | 1 | Forwards have faced NOT earlier this season |
| `team_week_standing` | 2 | Through gameweek 9 |
| `team_week_standing_opp` | 19 | Through gameweek 9 |
| `g_per_min_last_appearance` | 0.0 | 0 goals / 90 minutes |
| `g_per_min_season` | 0.01126 | 9 goals / 799 minutes |
| `positional_avg_g_per_min_last_appearance` | 0.00080 | Forwards who faced NOT in gameweeks 1–9, time-weighted |
| `positional_avg_g_per_min_season` | 0.00191 | Forwards who faced NOT in gameweeks 1–9, time-weighted |

## Targets and weights

These aren't features, but they determine what the features are used for. See [model.py](./model.py).

| Forest | Target | Games used | Game weight |
|---|---|---|---|
| Every stat except `cs` | Stat / minutes | Minutes above 0 | Minutes × recency |
| `cs` | Clean sheet (0 or 1) | 60+ minutes | Recency |

- **Recency:** a game's weight halves every 365 days (`RECENCY_HALF_LIFE_DAYS`), counted back from the latest
  training game.
- **Training rows:** every game before the predicted gameweek, including all stored past seasons.
- **Clean sheets:** they only count from 60 minutes (`CLEAN_SHEET_MINUTES`), so that forest predicts a chance per
  game instead of a rate.
- **Tree settings:** 300 trees per forest. Every leaf must hold at least 7,200 weighted minutes
  (`MIN_LEAF_MINUTES`), or 320 weighted games for `cs` (`MIN_LEAF_CLEAN_SHEET_GAMES`). Without this, a one-minute
  cameo can become an absurd per-90 number.

## Turning predictions into points

Each predicted rate is multiplied by that stat's scoring value for the position, using `FantasyScoringEngine`
rules, and the results are summed into a points-per-minute rate. For a given number of minutes:

```
points = per_min × minutes + (clean sheet chance × clean sheet points, if minutes >= 60)
```

## Players with no minutes this season

The forests aren't used for these players, whatever they did in earlier seasons
(`_use_position_rates_without_history` in [model.py](./model.py)). They get their position's actual output: total
stat divided by total minutes, and the clean sheet rate across games of 60+ minutes.

| Situation | Record used | `basis` |
|---|---|---|
| Position has 180+ minutes against this opponent this season | That record | `position_vs_opponent` |
| Fewer than 180 minutes against this opponent | Position against everyone this season | `position` |
| Gameweek 1 (no games yet this season) | Same two steps, using last season's games | either |

So in gameweek 1, every player at a position facing the same opponent gets the same number, and that week's
stored forests don't affect the prediction.

## Where the data comes from

| Data | Source |
|---|---|
| Stat lines, minutes, position | Fantrax player stats listing, one request set per gameweek |
| This season's fixtures and scores | Public FPL API |
| Past seasons' fixtures and scores | About 100 Fantrax game logs per season, stored in `fixtures.csv` |

Past-season players who changed clubs that season (labelled like `MUN/AVL`) are left out, because the listing
doesn't say which club each game was for. This season, they're placed at the last club listed.

## Adding a feature

1. Build it in [features.py](./features.py) using only earlier gameweeks' games, and in a way that works one season
   at a time.
2. Add it to `CONTEXT_FEATURES` or `feature_columns`.
3. Add its columns to `test_every_feature_ignores_its_own_and_later_gameweeks` if they aren't picked up automatically.
4. Run `python3 -m fpts_model.evaluate` after retraining, and keep it only if it beats the current numbers across
   most weeks. Delete the prediction files first to retrain them.

## Commands

Run these from `soccer/`:

```bash
pip install -r fpts_model/requirements.txt
python3 -m fpts_model.train                  # train whatever gameweek is due
python3 -m fpts_model.train --dry-run        # show what's due
python3 -m fpts_model.train --rebuild-models # recreate models missing from this machine
python3 -m fpts_model.train --fetch-history  # fetch past seasons not stored yet
python3 -m fpts_model.evaluate               # score predictions at actual minutes
```
