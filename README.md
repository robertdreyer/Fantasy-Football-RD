# Fantasy Football RD

Player ratings and fantasy point projections built from NFL play-by-play,
player-tracking (Next Gen Stats), coaching, schedule, and injury data.

## Pipeline

| Step | Script | Status |
|---|---|---|
| 1. Collect raw NFL data (2016–2025) | `collect_data.py` | ✅ |
| 2. Clean & load into a SQL database | — | planned |
| 3. Feature building (QB, OC tendencies, opposing DC, injury risk, separation, explosive runs) | — | planned |
| 4. Baseline + projection model, backtested vs. actual results | — | planned |
| 5. Website | — | planned |
| 6. Rookie projections from college data | — | planned |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python collect_data.py           # ~135 MB into data/raw/ (not committed)
```

## Data sources

- [nflverse](https://nflreadpy.nflverse.com/) via `nflreadpy`: play-by-play, weekly stats, Next Gen Stats, snap counts, injuries, schedules, rosters
- [DynastyProcess](https://github.com/dynastyprocess/data): cross-platform player ID map
