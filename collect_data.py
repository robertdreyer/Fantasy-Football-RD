"""
collect_data.py
Step 1 of the pipeline: download raw NFL data from nflverse and save it locally.

Nothing is transformed here. Keeping "raw" data separate from "cleaned" data
means you can always re-run later steps without downloading again.

Run it:  python collect_data.py
"""

from pathlib import Path

import nflreadpy as nfl  # returns Polars DataFrames

import polars as pl

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Next Gen Stats (separation, rush yards over expected) start in 2016,
# so that's a natural first season for a consistent dataset.
LAST_SEASON = 2025                 # freeze data here; 2026 is the test season
CUTOFF_DATE = "2026-09-09"         # 2026 kickoff, nothing on or after this date
SEASONS = list(range(2016, LAST_SEASON + 1))
PFR_SEASONS = list(range(2018, LAST_SEASON + 1))   # PFR advanced stats start in 2018

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
    url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
    save(pl.read_csv(url, infer_schema_length=10000, null_values=["NA"]), "ff_playerids")

# ---------------------------------------------------------------------------
# 5. Added datasets
# ---------------------------------------------------------------------------
print("Added datasets...")
save(nfl.load_participation(SEASONS), "participation")    # who was on the field, routes, man/zone coverage
save(nfl.load_combine(), "combine")                        # 40 time, vertical, etc. (all draft classes)
save(nfl.load_pfr_advstats(PFR_SEASONS, stat_type="rush"), "pfr_adv_rush")  # yards before/after contact
save(nfl.load_pfr_advstats(PFR_SEASONS, stat_type="rec"), "pfr_adv_rec")
save(nfl.load_ff_opportunity(SEASONS), "ff_opportunity")   # expected fantasy points from usage

# Expert consensus rankings (FantasyPros, archived by DynastyProcess).
# Same source as the player IDs, so same fallback.
try:
    ecr = nfl.load_ff_rankings("all")
except ConnectionError:
    url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr.parquet"
    ecr = pl.read_parquet(url)

# Keep only rankings published before the 2026 kickoff (no in-season leakage)
ecr = ecr.filter(pl.col("scrape_date") < CUTOFF_DATE)
save(ecr, "ecr_rankings")

# ---------------------------------------------------------------------------
# 6. Role, contracts and scheme data
# ---------------------------------------------------------------------------
print("Role, contracts and scheme data...")
# Depth charts changed format in 2025: weekly charts through 2024, timestamped
# snapshots from 2025 on. The 2026 file keeps only snapshots taken BEFORE kickoff.
save(nfl.load_depth_charts(list(range(2016, 2025))), "depth_charts_weekly")
dc_new = nfl.load_depth_charts([2025, 2026])
dc_new = dc_new.filter(pl.col("dt") < CUTOFF_DATE)   # timestamps like "2026-09-04T..." compare as text
save(dc_new, "depth_charts_daily")

save(nfl.load_ftn_charting(list(range(2022, LAST_SEASON + 1))), "ftn_charting")  # 2022+ hand charting
save(nfl.load_draft_picks(), "draft_picks")

trades = nfl.load_trades()
save(trades.filter(pl.col("trade_date").cast(pl.Utf8) < CUTOFF_DATE), "trades")

# Contracts (OverTheCap). Only a signing YEAR is available, not a date, so a
# handful of in-season 2026 extensions can slip in. Use with that caveat.
save(nfl.load_contracts(), "contracts")

# 2026 schedule: matchups only (who plays whom, when). Scores are dropped so no
# 2026 results enter the project. Used for next-season strength of schedule.
sched_2026 = nfl.load_schedules(2026).select(
    ["game_id", "season", "game_type", "week", "gameday", "home_team", "away_team"])
save(sched_2026, "schedule_2026")

print("\nDone.")
