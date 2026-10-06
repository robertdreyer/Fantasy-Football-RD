"""
collect_data.py
Step 1 of the pipeline: download raw NFL data from nflverse and save it locally.

Nothing is transformed here. Keeping "raw" data separate from "cleaned" data
means you can always re-run later steps without downloading again.

Run it:  python collect_data.py
"""

from pathlib import Path

import nflreadpy as nfl  # returns Polars DataFrames

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Next Gen Stats (separation, rush yards over expected) start in 2016,
# so that's a natural first season for a consistent dataset.
SEASONS = list(range(2016, 2026))  # 2016-2025

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)


def save(df, name):
    """Write a DataFrame to data/raw/<name>.parquet and print a quick summary."""
    path = RAW_DIR / f"{name}.parquet"
    df.write_parquet(path)
    print(f"  saved {name:<22} {df.height:>9,} rows x {df.width:>3} cols -> {path}")


# ---------------------------------------------------------------------------
# 1. Weekly player box scores
#    One row per player per game. Includes fantasy_points_ppr, target_share,
#    air_yards_share, wopr, and long-play counts: rushing_10 / rushing_20 /
#    rushing_40 = number of runs of 10+, 20+, 40+ yards (same for receiving).
# ---------------------------------------------------------------------------
print("Weekly player stats...")
save(nfl.load_player_stats(SEASONS, summary_level="week"), "player_stats_weekly")

# ---------------------------------------------------------------------------
# 2. Next Gen Stats (player-tracking data)
#    receiving: avg_separation, avg_cushion, avg_intended_air_yards,
#               avg_yac_above_expectation
#    rushing:   rush_yards_over_expected, efficiency,
#               percent_attempts_gte_eight_defenders (stacked boxes)
#    passing:   time to throw, aggressiveness, CPOE -- useful for the QB factor
#    NOTE: week 0 rows are season totals, weeks 1+ are single games.
#    Only players who clear a volume threshold appear each week.
# ---------------------------------------------------------------------------
print("Next Gen Stats...")
for stat_type in ["receiving", "rushing", "passing"]:
    save(nfl.load_nextgen_stats(SEASONS, stat_type=stat_type), f"ngs_{stat_type}")

# ---------------------------------------------------------------------------
# 3. Play-by-play (the big one: ~50k plays x 370+ columns per season)
#    This is where you'll build your own metrics: long-run rate by distance,
#    offensive tendencies (pass rate, pace, red-zone play calls), and defense
#    stats allowed. Saved one file per season to keep files manageable.
# ---------------------------------------------------------------------------
print("Play-by-play...")
for season in SEASONS:
    save(nfl.load_pbp(season), f"pbp_{season}")

# ---------------------------------------------------------------------------
# 4. Context tables
# ---------------------------------------------------------------------------
print("Context tables...")
save(nfl.load_snap_counts(SEASONS), "snap_counts")    # usage (2013+)
save(nfl.load_injuries(SEASONS), "injuries")          # weekly injury reports
save(nfl.load_schedules(SEASONS), "schedules")        # games, head coaches, Vegas lines
save(nfl.load_rosters(SEASONS), "rosters")            # player, team, position by season

# ID map linking gsis / sleeper / espn / pfr IDs. Hosted by a different project
# (DynastyProcess), so if that download fails we fall back to the raw file URL.
try:
    save(nfl.load_ff_playerids(), "ff_playerids")
except ConnectionError:
    import polars as pl
    url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
    save(pl.read_csv(url, infer_schema_length=10000, null_values=["NA"]), "ff_playerids")

print("\nDone.")
