# Running Back Data Dictionary

Every column relevant to running backs across the project's datasets.
Files live in `data/raw/`. Columns for kicking, punting, and defense are omitted.

**Joining tip:** `player_id` (player stats), `player_gsis_id` (NGS), `gsis_id` (injuries, rosters),
and `rusher_player_id` / `receiver_player_id` (play-by-play) are all the same ID.
Snap counts use `pfr_player_id` instead; link it through `rosters.pfr_id` or `ff_playerids`.

---

## 1. `player_stats_weekly.parquet`: box score, one row per player per game (1999+)

Filter RBs with `position == "RB"`.

### Identity and game
| Column | Description |
|---|---|
| `player_id` | nflverse / GSIS player ID (use this to join) |
| `player_name` | Short name, e.g. "S.Barkley" |
| `player_display_name` | Full name, e.g. "Saquon Barkley" |
| `position` / `position_group` | RB, WR, TE, QB, etc. |
| `headshot_url` | Link to player photo (useful for the website) |
| `season`, `week` | Season year and week number |
| `season_type` | `REG` (regular season) or `POST` (playoffs) |
| `game_id` | Game identifier, e.g. `2024_01_GB_PHI` |
| `team` / `opponent_team` | Player's team and the defense faced |

### Rushing
| Column | Description |
|---|---|
| `carries` | Rushing attempts |
| `rushing_yards` | Rushing yards |
| `rushing_tds` | Rushing touchdowns |
| `rushing_first_downs` | Carries that gained a first down |
| `rushing_fumbles` / `rushing_fumbles_lost` | Fumbles on runs / fumbles lost to the defense |
| `rushing_epa` | Total Expected Points Added on carries (value above an average play in the same situation) |
| `rushing_2pt_conversions` | Successful 2-point runs |
| `rushing_10` / `rushing_12` / `rushing_20` / `rushing_40` | Number of runs of 10+, 12+, 20+, 40+ yards (**long-run data**) |

### Receiving
| Column | Description |
|---|---|
| `targets` | Passes thrown to him |
| `receptions` | Catches |
| `receiving_yards` / `receiving_tds` | Receiving yards / touchdowns |
| `receiving_air_yards` | Yards the ball traveled in the air on his targets (often negative for RBs: screens, checkdowns) |
| `receiving_yards_after_catch` | Yards gained after the catch |
| `receiving_first_downs` | Catches that gained a first down |
| `receiving_fumbles` / `receiving_fumbles_lost` | Fumbles after catches / lost |
| `receiving_epa` | EPA on his targets |
| `receiving_2pt_conversions` | Successful 2-point catches |
| `receiving_10` / `_16` / `_20` / `_40` | Catches of 10+, 16+, 20+, 40+ yards |
| `target_share` | His share of the team's targets in that game |
| `air_yards_share` | His share of the team's air yards |
| `wopr` | Weighted Opportunity Rating = 1.5 × target share + 0.7 × air yards share (more useful for WRs) |
| `racr` | Receiving Air Conversion Ratio = receiving yards ÷ air yards |

### Other and fantasy
| Column | Description |
|---|---|
| `fumbles_total` / `fumbles_lost_total` | All fumbles / all fumbles lost |
| `special_teams_tds` | Return touchdowns |
| `kickoff_returns` / `kickoff_return_yards` | Kick return volume (some RBs return kicks) |
| `fantasy_points` | Standard-scoring fantasy points |
| `fantasy_points_ppr` | PPR fantasy points (1 point per catch). **This is the target you'll predict.** |

---

## 2. `ngs_rushing.parquet`: Next Gen Stats player tracking (2016+)

Week 0 = full-season totals; weeks 1+ = single games. Only players above a minimum carry count appear each week.

| Column | Description |
|---|---|
| `season`, `season_type`, `week` | When |
| `player_display_name`, `player_short_name`, `player_first_name`, `player_last_name` | Name fields |
| `player_position`, `player_jersey_number`, `team_abbr` | Position, jersey number, team |
| `player_gsis_id` | Player ID (joins to `player_id`) |
| `rush_attempts`, `rush_yards`, `avg_rush_yards`, `rush_touchdowns` | Standard rushing totals and yards per carry |
| `expected_rush_yards` | Yards an average back would gain given the blockers and defenders around him at handoff |
| `rush_yards_over_expected` | Actual minus expected yards (**best available measure of the runner's skill, separate from the offensive line**) |
| `rush_yards_over_expected_per_att` | Same, per carry |
| `rush_pct_over_expected` | % of carries where he beat the expected yards |
| `efficiency` | Distance he ran ÷ rushing yards gained. Lower = more north-south; higher = more east-west dancing |
| `percent_attempts_gte_eight_defenders` | % of carries against 8+ defenders in the box (stacked boxes = harder running) |
| `avg_time_to_los` | Average seconds from handoff to crossing the line of scrimmage (patient vs. hits the hole fast) |

---

## 3. `snap_counts.parquet`: playing time (2012+)

| Column | Description |
|---|---|
| `game_id` / `pfr_game_id` | Game identifiers (nflverse / Pro Football Reference) |
| `season`, `week`, `game_type` | When |
| `player`, `pfr_player_id`, `position` | Name, PFR ID, position |
| `team`, `opponent` | Teams |
| `offense_snaps` / `offense_pct` | Offensive snaps played / share of team's offensive snaps (**key for workload and committee backfields**) |
| `defense_snaps` / `defense_pct` | Defensive snaps (≈0 for RBs) |
| `st_snaps` / `st_pct` | Special teams snaps. A high share often means a backup |

---

## 4. `injuries.parquet`: weekly injury reports (2009+)

| Column | Description |
|---|---|
| `season`, `week`, `game_type`, `season_type`, `team` | When and which team |
| `gsis_id`, `full_name`, `first_name`, `last_name`, `position` | Who |
| `report_primary_injury` / `report_secondary_injury` | Injury listed on the official game-status report (e.g. Hamstring, Ankle) |
| `report_status` | Game status: Out, Doubtful, Questionable (blank = no designation) |
| `practice_primary_injury` / `practice_secondary_injury` | Injury listed on the practice report |
| `practice_status` | Practice participation: Did Not Participate, Limited, Full |
| `date_modified` | When the report was last updated |

---

## 5. `rosters.parquet`: player bio by season

| Column | Description |
|---|---|
| `season`, `week`, `game_type`, `team` | When and team |
| `position`, `depth_chart_position`, `ngs_position` | Position labels from different sources |
| `status`, `status_description_abbr` | Roster status (active, injured reserve, etc.) |
| `full_name`, `first_name`, `last_name`, `football_name` | Names (`football_name` = name he goes by) |
| `birth_date` | Date of birth (**compute age; RBs typically decline after ~27**) |
| `height`, `weight` | Size, in inches and pounds |
| `college` | College attended |
| `years_exp` | Years of NFL experience |
| `entry_year`, `rookie_year` | Year entered the league / rookie season |
| `draft_club`, `draft_number` | Team that drafted him and overall pick number (**draft capital**) |
| `jersey_number`, `headshot_url` | Jersey and photo |
| `gsis_id`, `espn_id`, `sleeper_id`, `yahoo_id`, `pfr_id`, `pff_id`, `rotowire_id`, `sportradar_id`, `fantasy_data_id`, `esb_id`, `gsis_it_id`, `smart_id` | IDs on other platforms, for joining |

---

## 6. `pbp_YYYY.parquet`: play-by-play (1999+)

372 columns; these are the ones that matter for RBs. A designed run is
`play_type == "run"` and `qb_scramble == 0`.

### Who and what
| Column | Description |
|---|---|
| `game_id`, `play_id`, `season`, `week`, `season_type` | Identify the play |
| `posteam` / `defteam` | Offense / defense |
| `play_type` | run, pass, punt, field_goal, etc. |
| `rusher_player_id`, `rusher_player_name` | Ball carrier on runs |
| `receiver_player_id`, `receiver_player_name` | Target on passes |
| `desc` | Text description of the play |
| `rushing_yards`, `receiving_yards`, `yards_gained` | Yards on the play |
| `rush_attempt`, `pass_attempt`, `complete_pass` | 1/0 flags |
| `rush_touchdown`, `pass_touchdown`, `touchdown` | 1/0 flags |
| `fumble`, `fumble_lost` | 1/0 flags |
| `first_down_rush`, `first_down` | Gained a first down |
| `tackled_for_loss` | Stopped behind the line |
| `qb_scramble`, `qb_kneel`, `two_point_attempt` | Plays to **exclude** from RB rushing analysis |
| `lateral_rush` | Play included a lateral |

### Situation (red zone, game script)
| Column | Description |
|---|---|
| `down`, `ydstogo` | Down and distance |
| `yardline_100` | Yards from opponent's end zone (≤20 = red zone, ≤5 = goal line: **touchdown opportunity**) |
| `goal_to_go` | 1 if goal-to-go |
| `qtr`, `game_seconds_remaining` | Game clock |
| `score_differential` | Offense's score minus defense's (**game script**: leading teams run more) |
| `wp` | Offense's win probability before the play |
| `shotgun`, `no_huddle` | Formation and tempo |
| `xpass` / `pass_oe` | Probability of a pass given the situation / pass rate over expected (**offensive coordinator tendency**) |

### Run details
| Column | Description |
|---|---|
| `run_location` | left, middle, right |
| `run_gap` | end, tackle, guard (for outside vs. inside runs) |

### Efficiency
| Column | Description |
|---|---|
| `epa` | Expected Points Added on the play |
| `success` | 1 if EPA > 0 (a "successful" play) |
| `ep`, `wpa` | Expected points before the play / win probability added |

### Pass-game details (RB receiving)
| Column | Description |
|---|---|
| `air_yards`, `yards_after_catch` | Depth of target and yards after the catch |
| `pass_location`, `pass_length` | Where the pass went |
| `xyac_mean_yardage` | Expected yards after the catch |

### Game context
| Column | Description |
|---|---|
| `home_team`, `away_team`, `home_coach`, `away_coach` | Teams and head coaches |
| `spread_line`, `total_line` | Vegas spread and over/under (**projected game script and scoring**) |
| `roof`, `surface`, `temp`, `wind`, `weather` | Stadium and weather conditions |
| `div_game` | Divisional game flag |

---

## Not downloaded yet (worth adding for RBs)

| Dataset | Loader | Key columns |
|---|---|---|
| PFR advanced rushing (2018+) | `nfl.load_pfr_advstats(seasons, stat_type="rush")` | `rushing_yards_before_contact(_avg)`, `rushing_yards_after_contact(_avg)`, `rushing_broken_tackles`, `receiving_broken_tackles`: separates the runner from his offensive line |
| Expected fantasy points | `nfl.load_ff_opportunity(seasons)` | `rush_fantasy_points_exp`, `total_fantasy_points_exp`, `*_diff`: how many points a player's usage *should* produce vs. what he scored. **Very predictive**, since usage is stickier than efficiency |
