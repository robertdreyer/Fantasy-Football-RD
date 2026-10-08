# Fantasy Football RD

**Live site:** https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/ (2026 predictions, graded every week)

Player ratings and fantasy point projections built from NFL play-by-play,
player-tracking (Next Gen Stats), coaching, schedule, and injury data.

## Pipeline

| Step | Script | Status |
|---|---|---|
| 1. Collect raw NFL data (2016–2025, frozen before the 2026 season) | `collect_data.py` | ✅ |
| 1b. Coaching staffs (HC/OC/DC by team-season) from Pro Football Reference | `collect_coordinators.py` → `reference/coordinators.csv` | ✅ |
| 2. Build one player-season table: production, per-route efficiency, coverage splits, red-zone role, health, depth charts, vacated targets, contracts, schedule, coaching, market rankings | `build_player_seasons.py` | ✅ |
| 2b. First analysis: what WRs look like the year before a breakout | `notebooks/wr_breakouts.ipynb` | ✅ |
| 2c. WR jump model walkthrough (JSN case study) | `notebooks/wr_jump_model.ipynb` | ✅ |
| 2d. RB and TE jump model walkthroughs | `notebooks/rb_jump_model.ipynb`, `notebooks/te_jump_model.ipynb` | ✅ |
| 3. Jump models for WR, TE, RB: predicted PPG change + leap probability, backtested 2019-2024 | `jump_model.py` → `predictions/` | ✅ |
| 4. Grade 2026 predictions against actual results as the season goes | `grade_2026.py` | ✅ (in progress) |
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
about +1.6 to +2.0 PPR points per game on average; the bottom 10% lost about 2.8 to 3.5.
Details: `predictions/backtest_summary.csv`. Live 2026 grading: `predictions/2026_grade_summary.csv`.

## Data sources

- [nflverse](https://nflreadpy.nflverse.com/) via `nflreadpy`: play-by-play, weekly stats, Next Gen Stats, snap counts, injuries, schedules, rosters
- [DynastyProcess](https://github.com/dynastyprocess/data): cross-platform player ID map and archived FantasyPros consensus rankings
- Pro Football Reference: advanced stats (via nflverse) and coaching staffs
- FTN charting, OverTheCap contracts, ESPN depth charts (via nflverse)

Column definitions: [`docs/player_seasons_columns.md`](docs/player_seasons_columns.md)
