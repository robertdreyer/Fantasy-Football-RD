# Fantasy Football RD

**Live site:** https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/ (2026 predictions, graded every week)

Player ratings and fantasy point projections built from NFL play-by-play,
player-tracking (Next Gen Stats), coaching, schedule, and injury data.

## Pipeline

| Step | Script | Status |
|---|---|---|
| 1. Collect raw NFL data (2016–2025, frozen before the 2026 season) | `collect_data.py` | ✅ |
| 1b. Coaching staffs (HC/OC/DC by team-season) from Pro Football Reference | `collect_coordinators.py` → `reference/coordinators.csv` | ✅ |
| 1c. Offensive play-callers 2016-2026, two sources per season where available (Wikipedia never the tiebreaker) | `build_play_caller_draft.py` → `build_play_callers.py` → `reference/play_callers.csv` | ✅ |
| 1d. Quarterback history 1999-2025, projected starter for every team 2016-2026, QB track records | `collect_qb_data.py` → `build_qb_seasons.py` → `data/processed/qb_seasons.parquet`, `reference/preseason_qbs.csv` | ✅ |
| 2. Build one player-season table: production, per-route efficiency, coverage splits, red-zone role, health, depth charts, vacated targets, contracts, schedule, coaching, market rankings | `build_player_seasons.py` | ✅ |
| 2b. First analysis: what WRs look like the year before a breakout | `notebooks/wr_breakouts.ipynb` | ✅ |
| 2c. WR jump model walkthrough (JSN case study) | `notebooks/wr_jump_model.ipynb` | ✅ |
| 2d. RB and TE jump model walkthroughs | `notebooks/rb_jump_model.ipynb`, `notebooks/te_jump_model.ipynb` | ✅ |
| 3. Jump models for WR, TE, RB: predicted PPG change + leap probability, backtested 2019-2024 | `jump_model.py` → `predictions/` | ✅ |
| 4. Grade 2026 predictions against actual results as the season goes | `grade_2026.py` | ✅ (in progress) |
| 4b. Model vs. expert rankings backtest | `market_test.py` → `predictions/market_backtest*.csv` | ✅ |
| 5. Website: predictions, per-player explanations, live grading | `build_site.py` → GitHub Pages | ✅ |
| 6. Weekly automation: grade + rebuild + publish every Tuesday | `.github/workflows/weekly-update.yml` | ✅ |
| 7. Rookie projections from college data | — | planned |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python collect_data.py           # raw data into data/raw/ (not committed)
python collect_coordinators.py   # ~25 min the first time; output is committed in reference/
python collect_qb_data.py        # QB history 1999-2015 + PFR advanced passing (once)
python build_qb_seasons.py       # -> qb_seasons, preseason starting QBs, QB track records
python build_player_seasons.py   # -> data/processed/player_seasons.parquet
python jump_model.py             # -> predictions/2026_jump_predictions.csv + backtest_summary.csv
python grade_2026.py             # compare predictions with 2026 results so far
python build_site.py             # -> site/index.html (open it in a browser to preview)
```

## Evaluation

All inputs stop at the end of the 2025 season, plus 2026 information known before kickoff
(preseason rankings, preseason depth charts, schedule matchups, coaching staffs).
The 2026 season is a true holdout used to grade the projections.

## Results so far

Backtest (each season predicted using only earlier seasons, 2019-2024): the models beat
"he'll repeat his baseline" at every position. Players in the top 10% of predicted change gained
about +1.6 to +2.1 PPR points per game on average; the bottom 10% lost about 2.9 to 3.9.
Details: `predictions/backtest_summary.csv`.

**Model vs. the experts** (`market_test.py`): expert consensus rankings still order drafted players a bit
better than the model overall, but the model adds information the experts miss (p = 0.02 after
controlling for expert rank). The edge is in the middle rounds: among players the experts ranked about
the same (2020-2025), middle-round picks the model liked more beat their expert rank 54% of the time,
vs. 33% for the ones it liked less; no edge on early picks. The site grades the 2026 middle-round picks
weekly. (A first version of this test overstated the edge, because "disagreement" and "beat the market"
both contain the expert rank; a placebo with random rankings caught it.)

Play-callers: when a team changes play-callers, the new caller's past offensive production
(points, yards, TDs, fantasy points; shrunk toward average) predicts the team's offense the next
season beyond what the team did the year before (2018-2025, 108 caller changes, p = 0.01).
For individual players it only helps running backs, so it's used in the RB model only.
Career table: `reference/play_caller_track_record.csv`.

Quarterbacks: a projected starter's track record (recent seasons weighted more, small samples pulled
toward what QBs from the same draft range did early in their careers) predicts his team's passing
efficiency the next season (p = 0.003). But it did not improve any position's player projections in
the backtest, so the QB-change columns are kept for analysis and the site shows each player's 2026 QB. Live 2026 grading: `predictions/2026_grade_summary.csv`.

## Data sources

- [nflverse](https://nflreadpy.nflverse.com/) via `nflreadpy`: play-by-play, weekly stats, Next Gen Stats, snap counts, injuries, schedules, rosters
- [DynastyProcess](https://github.com/dynastyprocess/data): cross-platform player ID map and archived FantasyPros consensus rankings
- Pro Football Reference: advanced stats (via nflverse) and coaching staffs
- FTN charting, OverTheCap contracts, ESPN depth charts (via nflverse)

Column definitions: [`docs/player_seasons_columns.md`](docs/player_seasons_columns.md)
