# `player_seasons` column guide

Built by `build_player_seasons.py` → `data/processed/player_seasons.parquet` (and `.csv`).
One row per player (WR, TE, RB) per regular season, 2016–2025. ~5,100 rows × 165 columns.

**Data through 2025 only.** 2026 inputs are limited to things known before the Sept. 9 kickoff:
preseason rankings, preseason depth charts, the schedule (matchups only) and coaching staffs.
They land in the `next_*` columns of 2025 rows. 2026 results are intentionally blank. They're the holdout.

## Identity
| Column | Meaning |
|---|---|
| `player_id` | nflverse/GSIS id (joins to every other nflverse table) |
| `name`, `position`, `season` | |
| `team` | Team at season's end · `n_teams` > 1 means traded mid-season |
| `age` | Age on Sept. 1 of that season |
| `years_exp`, `rookie_year` | NFL experience |

## Box score (regular season)
| Column | Meaning |
|---|---|
| `games`, `ppr`, `ppr_per_game` | Fantasy production (PPR) |
| `targets`, `receptions`, `rec_yards`, `rec_tds`, `air_yards`, `yac`, `rec_epa` | Receiving totals |
| `target_share`, `air_yards_share` | Average weekly share of team targets / air yards |
| `targets_per_game`, `yards_per_target`, `catch_rate` | Receiving rates |
| `carries`, `rush_yards`, `rush_tds`, `rush_epa`, `carries_per_game`, `yards_per_carry` | Rushing |
| `runs_10plus`, `runs_20plus`, `runs_40plus`, `explosive_run_rate` | Long runs (rate = 20+ yd runs per carry) |
| `run_10plus_rate` | Share of carries that gained 10+ yards (chunk runs) |
| `yac_per_reception` | Yards after the catch per reception |
| `fumbles_lost` | |

## Usage and talent
| Column | Meaning |
|---|---|
| `routes` | Dropbacks he was on the field for (≈ routes run; overstates TE/RB, who sometimes block) |
| `route_participation` | Share of team dropbacks he was on the field for (role / snap share on passing downs) |
| `tprr` | **Targets per route run.** Best free "earns targets" talent signal |
| `yprr` | **Yards per route run** |
| `routes_vs_man`, `tprr_vs_man`, `yprr_vs_man` (and `_vs_zone`) | Same, split by coverage (2018+). Man = beating a cornerback 1-on-1 |
| `avg_separation`, `avg_cushion`, `avg_intended_air_yards`, `avg_yac_above_expectation` | Next Gen Stats receiving (qualifying players only) |
| `ryoe_per_carry`, `rush_pct_over_expected` | Rush yards over expected: the runner's skill apart from blocking (NGS, qualifiers) |
| `rush_efficiency` | Distance run ÷ yards gained (lower = more north-south) |
| `pct_carries_8plus_box`, `avg_time_to_los` | Stacked boxes faced; patience behind the line |
| `ybc_per_carry` / `yac_per_carry` | Yards before contact (≈ blocking) / after contact (≈ the runner). PFR, 2018+ |
| `rush_broken_tackles`, `rec_broken_tackles`, `drops` | PFR charting, 2018+ |
| `xfp`, `xfp_per_game` | **Expected fantasy points**: what his usage should have scored |
| `fp_over_expected_per_game` | Actual − expected (standard scoring). + = efficient, but tends to regress |

## Scoring chances and role
| Column | Meaning |
|---|---|
| `rz_targets`, `rz_target_share` | Targets inside the 20, and his share of the team's |
| `ez_targets`, `ez_target_share` | Targets thrown into the end zone, and share |
| `rz_carries`, `rz_carry_share`, `gl_carries`, `gl_carry_share` | Red-zone and goal-line (inside the 5) carries, and shares |
| `deep_targets`, `deep_target_rate` | Targets 20+ yards downfield, and share of his targets |
| `adot` | Average depth of target (air yards ÷ targets): his role, deep vs. short |
| `catchable_target_rate`, `contested_target_rate` | Share of targets that were catchable / contested (FTN charting, 2022+). Low catchable = QB holding him back |
| `preseason_depth_tier` | Depth chart before that season's kickoff. 1 = starter (WR1-3, RB1, TE1), 2 = next group, ... |

## Consistency
| Column | Meaning |
|---|---|
| `ppr_weekly_sd` | Week-to-week standard deviation of PPR points |
| `boom_rate`, `bust_rate` | Share of games with 20+ / under 5 PPR points |
| `first_half_ppg`, `second_half_ppg`, `second_half_trend` | Weeks 1-9 vs. 10+; positive trend = finished strong (often a role increase) |

## Health
| Column | Meaning |
|---|---|
| `games_missed` | Team games he didn't play (any reason: injury, inactive, benched) |
| `games_missed_last3` | Same, summed over this season and the two before |
| `weeks_listed_out` | Weeks ruled Out on the injury report |
| `weeks_dnp_practice` | Weeks with a Did Not Participate practice listing |
| `soft_tissue_reports` | Injury-report weeks for hamstring / groin / calf / quad (these tend to recur) |

## Bio and athleticism
| Column | Meaning |
|---|---|
| `draft_pick` | Overall pick (blank = undrafted) |
| `height`, `weight` | Inches, pounds |
| `forty`, `vertical`, `broad_jump`, `cone`, `shuttle` | Combine results |
| `speed_score` | weight × 200 ÷ forty⁴: speed adjusted for size (~100 avg for RBs) |
| `pfr_id` | Pro Football Reference id |

## Team context (his team that season)
| Column | Meaning |
|---|---|
| `qb_name`, `qb_epa_per_dropback`, `qb_cpoe` | Primary QB (most dropbacks) and his efficiency |
| `team_epa_per_dropback`, `team_epa_per_rush` | Offense efficiency |
| `team_pass_rate_over_exp` | Passes more (+) or less (−) than expected given the situation: play-caller tendency |
| `team_dropbacks_per_game` | Pass volume |
| `team_rz_plays_per_game` | Red-zone plays per game: scoring chances |
| `team_8plus_box_rate` | Share of runs vs. 8+ in the box: high = defenses don't fear the pass |
| `team_run_stuff_rate` | Share of runs for ≤ 0 yards: poor run blocking |
| `team_pressure_rate_allowed` | Share of dropbacks where the QB was pressured: pass protection |
| `team_motion_rate`, `team_play_action_rate`, `team_screen_rate` | Scheme tendencies on dropbacks (FTN, 2022+) |
| `head_coach`, `oc`, `dc` | Coaching staff (appear once `reference/coordinators.csv` exists) |

## Market vs. results (2020+)
| Column | Meaning |
|---|---|
| `preseason_rank` | FantasyPros PPR positional consensus rank, last snapshot before kickoff |
| `preseason_ecr`, `preseason_ecr_sd` | Average expert rank, and how much experts disagreed |
| `finish_rank` | Actual positional finish by total PPR points |
| `finish_rank_ppg` | Finish by points per game (6+ games) |
| `outperformance` | `preseason_rank − finish_rank`. Positive = beat the market |

## Next season (what you predict)
| Column | Meaning |
|---|---|
| `next_team`, `next_games`, `next_ppr`, `next_ppr_per_game`, `next_finish_rank` | Following season's results (blank for 2025 rows: holdout) |
| `next_preseason_rank`, `next_preseason_ecr`, `next_preseason_ecr_sd`, `next_preseason_team` | Following season's preseason market (2025 rows = 2026 preseason) |
| `next_outperformance` | Next season's preseason rank − finish rank |
| `next_preseason_team` | Team on the next preseason depth chart (FantasyPros team as backup) |
| `next_preseason_depth_tier` | His depth-chart tier entering next season |
| `next_team_vacated_target_share`, `next_team_vacated_carry_share` | Share of his next team's targets/carries from this season that belonged to players no longer on its preseason depth chart: **opportunity opening up** |
| `next_contract_apy_cap_pct`, `next_contract_guaranteed_m`, `next_contract_new` | Contract covering next season: salary as % of cap, guaranteed $ (millions), 1 if newly signed. Caveat: only a signing *year* exists, so a few in-season extensions can slip in |
| `next_sos_pass_def_epa`, `next_sos_rush_def_epa` | Next season's opponents' defensive EPA allowed in the season just played. Higher = easier schedule. Weak signal: defenses change year to year |
| `next_head_coach`, `next_oc`, `next_dc` | Next season's staff on his next team (with coordinators file) |
| `next_oc_prior_pass_rate_over_exp` | The incoming OC's pass rate over expected in his most recent season as an OC: tendency that travels with the coordinator |
| `team_carry_share`, `team_target_share_season` | His share of his team's carries / targets this season (among WR, TE, RB) |
| `next_competition_carry_share`, `next_competition_target_share` | Share of his NEXT team's carries / targets this season held by other players who are still on its preseason depth chart: **returning competition** |
| `carry_share_gap`, `target_share_gap` | Work not held by returning teammates, minus what he already had (+ = room to grow) |
| `open_carries_per_game`, `open_targets_per_game` | Carries / targets per game left on his next team after returning teammates' share |
| `open_carries_vs_current`, `open_targets_vs_current` | Those open amounts minus his current per-game workload |
| `changed_team` | 1 if his next-preseason team differs from this season's |
| `oc_changed` | 1 if his offensive coordinator will be different next season |

## Play-callers (from `reference/play_callers.csv`, researched with sources)
Style numbers describe the offense a caller ran; for next season we use the incoming caller's most
recent season calling plays (any team), never anything from the season being predicted.
Coverage is incomplete until 2016, 2017 and 2019 are researched, so the models don't use these yet.

| Column | Meaning |
|---|---|
| `play_caller` | Who called his team's offensive plays at the start of this season |
| `next_play_caller` | Who will call plays for his next-preseason team |
| `play_caller_changed` | 1 if next season's caller is a different person |
| `next_caller_first_time` | 1 if the incoming caller has no play-calling seasons in the table |
| `next_caller_seasons_before` | Play-calling seasons the incoming caller has in the table |
| `next_caller_pass_rate_over_exp`, `next_caller_dropbacks_per_game` | Incoming caller's pass tendency and pass volume |
| `next_caller_rb_target_share`, `next_caller_te_target_share`, `next_caller_top_target_share` | How his offense spread targets: to RBs, to TEs, and to its top target |
| `next_caller_motion_rate`, `next_caller_play_action_rate` | His motion and play-action rates (2022+) |
| `next_caller_*_shift` | Incoming caller's style minus what the player's team ran this season (+ = more of it) |
