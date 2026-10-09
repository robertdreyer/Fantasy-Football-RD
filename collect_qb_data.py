"""
collect_qb_data.py
Step 1b: download quarterback history that collect_data.py doesn't already have.

collect_data.py covers 2016-2025 for every position. A quarterback's track record often starts
earlier (Aaron Rodgers started in 2008), so this adds:
  - weekly QB box scores 1999-2015 (passing + rushing, EPA, CPOE, air yards, fantasy points)
  - Pro Football Reference advanced passing 2018-2025 (pressures, bad throws, time in pocket)

Same holdout rule as everything else: nothing after the 2025 season.

Run it once:  python collect_qb_data.py     (about a minute)
"""

from pathlib import Path

import nflreadpy as nfl
import polars as pl

FIRST_SEASON = 1999                     # first season nflverse player stats cover
HISTORY_SEASONS = list(range(FIRST_SEASON, 2016))   # 2016+ is already in player_stats_weekly
PFR_SEASONS = list(range(2018, 2026))

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)


def save(df, name):
    path = RAW_DIR / f"{name}.parquet"
    df.write_parquet(path)
    print(f"  saved {name:<26} {df.height:>9,} rows x {df.width:>3} cols -> {path}")


print(f"Weekly QB stats {FIRST_SEASON}-2015...")
old = nfl.load_player_stats(HISTORY_SEASONS, summary_level="week")
save(old.filter(pl.col("position") == "QB"), "qb_stats_weekly_1999_2015")

print("PFR advanced passing 2018-2025 (season totals)...")
save(nfl.load_pfr_advstats(PFR_SEASONS, stat_type="pass", summary_level="season"), "pfr_adv_pass")

print("Done. Next: python build_qb_seasons.py")
