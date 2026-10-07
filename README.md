# Fantasy Football RD

Player ratings and fantasy point projections built from NFL play-by-play,
player-tracking (Next Gen Stats), coaching, schedule, and injury data.

## Pipeline

| Step | Script | Status |
|---|---|---|
| 1. Collect raw NFL data (2016–2025, frozen before the 2026 season) | `collect_data.py` | ✅ |
| 1b. Coaching staffs (HC/OC/DC by team-season) from Pro Football Reference | `collect_coordinators.py` → `reference/coordinators.csv` | ✅ |
| 2. Build one player-season table: production, per-route efficiency, coverage splits, red-zone role, health, depth charts, vacated targets, contracts, schedule, coaching, market rankings | `build_player_seasons.py` | ✅ |
| 2b. First analysis: what WRs look like the year before a breakout | `notebooks/wr_breakouts.ipynb` | ✅ |
| 3. Feature building (QB, OC tendencies, opposing DC, injury risk, separation, explosive runs) | — | planned |
| 4. Baseline + projection model, backtested vs. actual results | — | planned |
| 5. Website | — | planned |
| 6. Rookie projections from college data | — | planned |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python collect_data.py           # raw data into data/raw/ (not committed)
python collect_coordinators.py   # ~25 min the first time; output is committed in reference/
python build_player_seasons.py   # -> data/processed/player_seasons.parquet
```

## Evaluation

All inputs stop at the end of the 2025 season, plus 2026 information known before kickoff
(preseason rankings, preseason depth charts, schedule matchups, coaching staffs).
The 2026 season is a true holdout used to grade the projections.

## Data sources

- [nflverse](https://nflreadpy.nflverse.com/) via `nflreadpy`: play-by-play, weekly stats, Next Gen Stats, snap counts, injuries, schedules, rosters
- [DynastyProcess](https://github.com/dynastyprocess/data): cross-platform player ID map and archived FantasyPros consensus rankings
- Pro Football Reference: advanced stats (via nflverse) and coaching staffs
- FTN charting, OverTheCap contracts, ESPN depth charts (via nflverse)

Column definitions: [`docs/player_seasons_columns.md`](docs/player_seasons_columns.md)
