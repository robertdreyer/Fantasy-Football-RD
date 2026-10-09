# Quarterback tables (`build_qb_seasons.py`)

## `data/processed/qb_seasons.parquet` — one row per QB per regular season, 1999-2025
Sources: nflverse weekly player stats (1999+), play-by-play (2016+), Next Gen Stats (2016+),
Pro Football Reference advanced passing (2018+), draft picks, rosters.

| Column | Meaning |
|---|---|
| `player_id`, `name`, `team`, `season` | gsis ID, name, team he played most for |
| `games`, `starts` | Games played; starts = games where he had the most dropbacks for his team (10+) |
| `dropbacks` | Pass attempts + sacks |
| `epa_per_dropback` | Expected points added per dropback: the best single measure of QB play |
| `cpoe` | Completion % over expected (2006+) |
| `any_a` | Adjusted net yards per attempt: (yards + 20·TD − 45·INT − sack yards) / dropbacks |
| `comp_pct`, `td_rate`, `int_rate`, `sack_rate`, `adot` | Completion %, TD and INT per attempt, sacks per dropback, average depth of target |
| `pass_yds_per_game`, `rush_yds_per_game`, `carries_per_game`, `fantasy_ppg` | Per-game production (fantasy = standard QB scoring) |
| `draft_year`, `draft_round`, `draft_pick`, `draft_group`, `age` | Draft capital (round 1 / rounds 2-3 / later or undrafted) and age |
| `designed_runs`, `scrambles`, `goal_line_runs` | His runs, from play-by-play (2016+) |
| `qb_rush_share`, `qb_goal_line_share`, `scramble_rate` | Share of team runs (and runs inside the 5) he took; scrambles per dropback |
| `deep_attempt_rate`, `rb_target_share`, `te_target_share`, `wr_target_share`, `top_target_share` | Passing style: deep throws, where his targets went |
| `avg_time_to_throw`, `aggressiveness`, `avg_air_yards_differential` | Next Gen Stats (2016+) |
| `pressure_pct`, `bad_throw_pct`, `on_tgt_pct`, `pocket_time` | PFR charting (2018+) |

## `reference/preseason_qbs.csv` — projected starter for every team, 2016-2026
`qb_id`, `qb_name`, `source` (which depth chart), `actual_main_qb` (most dropbacks for that team that
season; blank for 2026), `projected_starter_was_main_qb`. The projected starter was the main QB in
85% of 2016-2025 team-seasons; the rest are injuries and benchings, which can't be known before kickoff.
All 32 projected 2026 starters were checked against Week 1 reporting.

## `data/processed/qb_records.parquet` — track record entering each season, 2016-2026
Built only from earlier seasons. Each season back counts 60% as much as the one after it.
Efficiency stats are blended with 400 dropbacks of a starting point (what QBs from the same draft range
did in their first two seasons, using only seasons before), per-game stats with 6 games of it, so a
backup or rookie gets a sensible estimate. Columns: `qb_rec_<stat>` for the stats above, plus
`qb_seasons_before`, `qb_starts_before`, `qb_dropbacks_before`, `qb_seasons_since_last_start`.

## `data/processed/team_qb_dropbacks.parquet`
Each QB's share of his team's dropbacks per season (2016-2025), used to blend "this season's QB play".
