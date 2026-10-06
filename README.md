# Fantasy Football RD

Player ratings and fantasy point projections built from NFL play-by-play,
player-tracking (Next Gen Stats), coaching, schedule, and injury data.

## Pipeline

| Step | Script | Status |
|---|---|---|
| 1. Collect raw NFL data (2016–2025, frozen before the 2026 season) | `collect_data.py` | ✅ |
| 2. Build one player-season table (box score, routes, NGS, PFR, team context, rankings) | `build_player_seasons.py` | ✅ |
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
python build_player_seasons.py   # -> data/processed/player_seasons.parquet
```

## Evaluation

All inputs stop at the end of the 2025 season (plus 2026 *preseason* rankings).
The 2026 season is a true holdout used to grade the projections.

## Data sources

- [nflverse](https://nflreadpy.nflverse.com/) via `nflreadpy`: play-by-play, weekly stats, Next Gen Stats, snap counts, injuries, schedules, rosters
- [DynastyProcess](https://github.com/dynastyprocess/data): cross-platform player ID map and archived FantasyPros consensus rankings
- Pro Football Reference advanced stats (via nflverse)
