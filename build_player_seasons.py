"""
build_player_seasons.py
Step 2 of the pipeline: turn the raw nflverse files into ONE analysis table.

Output: data/processed/player_seasons.parquet (+ a .csv copy for Excel)
        One row per player (WR, TE, RB) per regular season, 2016-2025.

Each row has six groups of columns:
  1. Box score       - games, targets, carries, yards, TDs, fantasy points
  2. Usage & talent  - routes run, targets/yards per route run, man vs. zone splits,
                       Next Gen Stats, PFR charting, expected fantasy points
  3. Bio             - age, experience, draft pick, size, combine, speed score
  4. Team context    - QB, pass rate over expected, efficiency, red-zone volume,
                       stacked boxes, run blocking
  5. Market          - preseason expert consensus rank (2020+) and actual finish
  6. Next season     - what happened the FOLLOWING year (the thing we predict),
                       including "next_outperformance" = preseason rank - finish rank

Leakage rule: only data through the 2025 season is used. The one 2026 input is the
2026 PRESEASON ranking (published before the Sept. 9 kickoff), which fills
next_preseason_rank for 2025 rows. 2026 outcomes are left blank on purpose:
they are the holdout we grade the model on.

Run it:  python build_player_seasons.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

SEASONS = list(range(2016, 2026))
POSITIONS = ["WR", "TE", "RB"]
KICKOFF_2026 = "2026-09-09"

# FantasyPros team codes -> nflverse team codes
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "OAK": "LV", "SD": "LAC", "STL": "LA"}


def per(num, den):
    """Safe division: returns NaN instead of an error/inf when the denominator is 0."""
    return np.where(den > 0, num / den.replace(0, np.nan), np.nan)


# ===========================================================================
# 1. BOX SCORE: season totals from weekly stats
# ===========================================================================
print("1. Box score totals...")
stats = pd.read_parquet(RAW / "player_stats_weekly.parquet")
stats = stats[(stats["season_type"] == "REG") & stats["position"].isin(POSITIONS)]

box = (
    stats.groupby(["player_id", "season"])
    .agg(
        name=("player_display_name", "last"),
        position=("position", "last"),
        team=("team", "last"),                    # team at season's end
        n_teams=("team", "nunique"),               # >1 = traded mid-season
        games=("game_id", "nunique"),
        targets=("targets", "sum"),
        receptions=("receptions", "sum"),
        rec_yards=("receiving_yards", "sum"),
        rec_tds=("receiving_tds", "sum"),
        air_yards=("receiving_air_yards", "sum"),
        yac=("receiving_yards_after_catch", "sum"),
        rec_epa=("receiving_epa", "sum"),
        target_share=("target_share", "mean"),
        air_yards_share=("air_yards_share", "mean"),
        carries=("carries", "sum"),
        rush_yards=("rushing_yards", "sum"),
        rush_tds=("rushing_tds", "sum"),
        rush_epa=("rushing_epa", "sum"),
        runs_10plus=("rushing_10", "sum"),
        runs_20plus=("rushing_20", "sum"),
        runs_40plus=("rushing_40", "sum"),
        fumbles_lost=("fumbles_lost_total", "sum"),
        ppr=("fantasy_points_ppr", "sum"),
    )
    .reset_index()
)
box["ppr_per_game"] = box["ppr"] / box["games"]
box["targets_per_game"] = box["targets"] / box["games"]
box["carries_per_game"] = box["carries"] / box["games"]
box["yards_per_target"] = per(box["rec_yards"], box["targets"])
box["yards_per_carry"] = per(box["rush_yards"], box["carries"])
box["catch_rate"] = per(box["receptions"], box["targets"])
box["explosive_run_rate"] = per(box["runs_20plus"], box["carries"])


# ===========================================================================
# 2a. ROUTES RUN, from participation (who was on the field) + play-by-play
#     A "route" = a pass play (dropback) where the player was on the field.
#     Very accurate for WRs; for TEs/RBs it also counts plays where they stayed
#     in to block, so treat their route numbers as an upper bound.
# ===========================================================================
print("2. Routes run, per-route efficiency, man/zone splits...")
part = pd.read_parquet(
    RAW / "participation.parquet",
    columns=["nflverse_game_id", "play_id", "offense_players", "defense_man_zone_type"],
)
part = part.rename(columns={"nflverse_game_id": "game_id"})

PBP_COLS = ["game_id", "play_id", "season", "season_type", "posteam", "defteam", "play_type",
            "qb_dropback", "rush_attempt", "qb_scramble", "two_point_attempt", "pass_attempt",
            "receiver_player_id", "receiving_yards", "rushing_yards", "passer_player_id",
            "passer_player_name", "epa", "pass_oe", "cpoe", "yardline_100", "down"]
pbp = pd.concat(
    [pd.read_parquet(RAW / f"pbp_{s}.parquet", columns=PBP_COLS) for s in SEASONS],
    ignore_index=True,
)
pbp = pbp[(pbp["season_type"] == "REG") & (pbp["two_point_attempt"] == 0)]

dropbacks = pbp[pbp["qb_dropback"] == 1].merge(part, on=["game_id", "play_id"], how="inner")
dropbacks = dropbacks[dropbacks["offense_players"].fillna("") != ""]
dropbacks["coverage"] = dropbacks["defense_man_zone_type"].map(
    {"MAN_COVERAGE": "man", "ZONE_COVERAGE": "zone"}
)

# One row per (play, offensive player on the field)
on_field = dropbacks[["game_id", "play_id", "season", "posteam", "coverage",
                      "offense_players", "receiver_player_id", "receiving_yards"]].copy()
on_field["player_id"] = on_field["offense_players"].str.split(";")
on_field = on_field.explode("player_id")
on_field["targeted"] = (on_field["player_id"] == on_field["receiver_player_id"]).astype(int)
on_field["route_yards"] = np.where(on_field["targeted"] == 1, on_field["receiving_yards"].fillna(0), 0)

routes = (
    on_field.groupby(["player_id", "season"])
    .agg(routes=("play_id", "size"), route_targets=("targeted", "sum"),
         route_yards=("route_yards", "sum"))
    .reset_index()
)

# Same thing split by coverage (charting starts in 2018)
cov = (
    on_field.dropna(subset=["coverage"])
    .groupby(["player_id", "season", "coverage"])
    .agg(r=("play_id", "size"), t=("targeted", "sum"), y=("route_yards", "sum"))
    .unstack("coverage")
)
cov.columns = [f"{stat}_{c}" for stat, c in cov.columns]
cov = cov.reset_index()
for c in ["man", "zone"]:
    cov[f"tprr_vs_{c}"] = per(cov[f"t_{c}"], cov[f"r_{c}"])
    cov[f"yprr_vs_{c}"] = per(cov[f"y_{c}"], cov[f"r_{c}"])
    cov = cov.rename(columns={f"r_{c}": f"routes_vs_{c}"})
cov = cov[["player_id", "season", "routes_vs_man", "routes_vs_zone",
           "tprr_vs_man", "tprr_vs_zone", "yprr_vs_man", "yprr_vs_zone"]]

# Team dropbacks (with participation data) -> share of dropbacks each player was out there
team_db = dropbacks.groupby(["posteam", "season"]).size().rename("team_charted_dropbacks")
player_team = on_field.groupby(["player_id", "season"])["posteam"].agg(lambda s: s.mode().iat[0])
routes = routes.merge(player_team.rename("route_team"), on=["player_id", "season"])
routes = routes.merge(team_db, left_on=["route_team", "season"], right_index=True)
routes["route_participation"] = routes["routes"] / routes["team_charted_dropbacks"]
routes["tprr"] = per(routes["route_targets"], routes["routes"])   # targets per route run
routes["yprr"] = per(routes["route_yards"], routes["routes"])     # yards per route run
routes = routes.drop(columns=["route_team", "team_charted_dropbacks", "route_targets", "route_yards"])


# ===========================================================================
# 2b. NEXT GEN STATS (week 0 = full-season row)
# ===========================================================================
print("3. Next Gen Stats, PFR charting, expected fantasy points...")
ngs_rec = pd.read_parquet(RAW / "ngs_receiving.parquet")
ngs_rec = ngs_rec[(ngs_rec["week"] == 0) & (ngs_rec["season_type"] == "REG")]
ngs_rec = ngs_rec[["player_gsis_id", "season", "avg_separation", "avg_cushion",
                   "avg_intended_air_yards", "avg_yac_above_expectation"]]

ngs_rush = pd.read_parquet(RAW / "ngs_rushing.parquet")
ngs_rush = ngs_rush[(ngs_rush["week"] == 0) & (ngs_rush["season_type"] == "REG")]
ngs_rush = ngs_rush[["player_gsis_id", "season", "rush_yards_over_expected_per_att",
                     "rush_pct_over_expected", "efficiency",
                     "percent_attempts_gte_eight_defenders", "avg_time_to_los"]]
ngs_rush = ngs_rush.rename(columns={"rush_yards_over_expected_per_att": "ryoe_per_carry",
                                    "efficiency": "rush_efficiency",
                                    "percent_attempts_gte_eight_defenders": "pct_carries_8plus_box"})
ngs = ngs_rec.merge(ngs_rush, on=["player_gsis_id", "season"], how="outer")
ngs = ngs.rename(columns={"player_gsis_id": "player_id"})


# ===========================================================================
# 2c. PFR CHARTING (2018+): contact, broken tackles, drops. Keyed by PFR id.
# ===========================================================================
pfr_rush = pd.read_parquet(RAW / "pfr_adv_rush.parquet")
pfr_rush = pfr_rush[pfr_rush["game_type"] == "REG"]
pfr_rush = pfr_rush.groupby(["pfr_player_id", "season"]).agg(
    pfr_carries=("carries", "sum"),
    yards_before_contact=("rushing_yards_before_contact", "sum"),
    yards_after_contact=("rushing_yards_after_contact", "sum"),
    rush_broken_tackles=("rushing_broken_tackles", "sum"),
).reset_index()
pfr_rush["ybc_per_carry"] = per(pfr_rush["yards_before_contact"], pfr_rush["pfr_carries"])  # ~ blocking
pfr_rush["yac_per_carry"] = per(pfr_rush["yards_after_contact"], pfr_rush["pfr_carries"])   # ~ the runner
pfr_rush = pfr_rush.drop(columns=["pfr_carries", "yards_before_contact", "yards_after_contact"])

pfr_rec = pd.read_parquet(RAW / "pfr_adv_rec.parquet")
pfr_rec = pfr_rec[pfr_rec["game_type"] == "REG"]
pfr_rec = pfr_rec.groupby(["pfr_player_id", "season"]).agg(
    rec_broken_tackles=("receiving_broken_tackles", "sum"),
    drops=("receiving_drop", "sum"),
).reset_index()

pfr = pfr_rush.merge(pfr_rec, on=["pfr_player_id", "season"], how="outer")


# ===========================================================================
# 2d. EXPECTED FANTASY POINTS: what a player's usage "should" have scored
# ===========================================================================
opp = pd.read_parquet(RAW / "ff_opportunity.parquet")
opp["season"] = opp["season"].astype(int)
reg_games = pd.read_parquet(RAW / "schedules.parquet").query("game_type == 'REG'")["game_id"]
opp = opp[opp["game_id"].isin(reg_games)]
opp = opp.groupby(["player_id", "season"]).agg(
    xfp=("total_fantasy_points_exp", "sum"),
    fp_std=("total_fantasy_points", "sum"),
).reset_index()


# ===========================================================================
# 3. BIO: age, experience, draft capital, size, combine
# ===========================================================================
print("4. Bio and combine...")
rosters = pd.read_parquet(RAW / "rosters.parquet")
bio = (
    rosters.dropna(subset=["gsis_id"])
    .sort_values("week")
    .groupby(["gsis_id", "season"])
    .agg(pfr_id=("pfr_id", "last"), birth_date=("birth_date", "last"),
         years_exp=("years_exp", "last"), rookie_year=("rookie_year", "last"),
         draft_pick=("draft_number", "last"), height=("height", "last"),
         weight=("weight", "last"))
    .reset_index()
    .rename(columns={"gsis_id": "player_id"})
)
# Age on Sept. 1 of that season
bio["age"] = ((pd.to_datetime(bio["season"].astype(str) + "-09-01")
               - pd.to_datetime(bio["birth_date"], errors="coerce")).dt.days / 365.25).round(1)
bio = bio.drop(columns=["birth_date"])
# Draft pick never changes, but some seasons' rosters leave it blank: fill from the player's other seasons
bio["draft_pick"] = bio.groupby("player_id")["draft_pick"].transform("max")   # still blank = undrafted

combine = pd.read_parquet(RAW / "combine.parquet")
combine = (combine.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id", keep="last")
           [["pfr_id", "forty", "vertical", "broad_jump", "cone", "shuttle", "wt"]])
# Speed score: 40 time adjusted for size (bigger + fast = rarer). ~100 is average for RBs.
combine["speed_score"] = (combine["wt"] * 200 / combine["forty"] ** 4).round(1)
combine = combine.drop(columns=["wt"])


# ===========================================================================
# 4. TEAM CONTEXT (team-season): QB, play-calling, efficiency, blocking
# ===========================================================================
print("5. Team context...")
off = pbp[pbp["play_type"].isin(["pass", "run"])]
db = off[off["qb_dropback"] == 1]
runs = off[(off["rush_attempt"] == 1) & (off["qb_scramble"] == 0)]

games_per_team = pbp.groupby(["posteam", "season"])["game_id"].nunique().rename("team_games")
team = pd.concat(
    [
        games_per_team,
        db.groupby(["posteam", "season"]).size().rename("team_dropbacks"),
        db.groupby(["posteam", "season"])["epa"].mean().rename("team_epa_per_dropback"),
        runs.groupby(["posteam", "season"])["epa"].mean().rename("team_epa_per_rush"),
        off.groupby(["posteam", "season"])["pass_oe"].mean().rename("team_pass_rate_over_exp"),
        off[off["yardline_100"] <= 20].groupby(["posteam", "season"]).size().rename("team_rz_plays"),
        runs.assign(stuff=runs["rushing_yards"] <= 0)
            .groupby(["posteam", "season"])["stuff"].mean().rename("team_run_stuff_rate"),
    ],
    axis=1,
).reset_index().rename(columns={"posteam": "team"})
team["team_dropbacks_per_game"] = team["team_dropbacks"] / team["team_games"]
team["team_rz_plays_per_game"] = team["team_rz_plays"] / team["team_games"]
team = team.drop(columns=["team_dropbacks", "team_rz_plays", "team_games"])

# Stacked boxes faced on runs: high = defenses don't fear the pass.
# Uses Next Gen Stats (consistent definition across all seasons), weighted by carries.
ngs_box = pd.read_parquet(RAW / "ngs_rushing.parquet")
ngs_box = ngs_box[(ngs_box["week"] == 0) & (ngs_box["season_type"] == "REG")].dropna(subset=["team_abbr"])
ngs_box["stacked_carries"] = ngs_box["percent_attempts_gte_eight_defenders"] / 100 * ngs_box["rush_attempts"]
box8 = ngs_box.groupby(["team_abbr", "season"])[["stacked_carries", "rush_attempts"]].sum()
box8["team_8plus_box_rate"] = box8["stacked_carries"] / box8["rush_attempts"]
box8 = box8[["team_8plus_box_rate"]].reset_index().rename(columns={"team_abbr": "team"})
team = team.merge(box8, on=["team", "season"], how="left")

# Primary QB = most dropbacks for that team-season
qb = (db.dropna(subset=["passer_player_id"])
      .groupby(["posteam", "season", "passer_player_id", "passer_player_name"])
      .agg(qb_dropbacks=("play_id", "size"), qb_epa_per_dropback=("epa", "mean"),
           qb_cpoe=("cpoe", "mean"))
      .reset_index()
      .sort_values("qb_dropbacks")
      .drop_duplicates(["posteam", "season"], keep="last")
      .rename(columns={"posteam": "team", "passer_player_name": "qb_name"})
      .drop(columns=["passer_player_id", "qb_dropbacks"]))
team = team.merge(qb, on=["team", "season"], how="left")


# ===========================================================================
# 5. MARKET: preseason expert consensus rank (positional, PPR) + actual finish
# ===========================================================================
print("6. Preseason rankings and finishes...")
ecr = pd.read_parquet(RAW / "ecr_rankings.parquet",
                      columns=["fp_page", "scrape_date", "id", "player", "pos", "team", "ecr", "sd"])
ecr = ecr[ecr["fp_page"].str.contains(r"(?:^|/)ppr-(?:wr|rb|te)-cheatsheets")]
ecr["season"] = ecr["scrape_date"].str[:4].astype(int)

kickoff = (pd.read_parquet(RAW / "schedules.parquet").query("game_type == 'REG'")
           .groupby("season")["gameday"].min().to_dict())
kickoff[2026] = KICKOFF_2026
ecr = ecr[ecr["season"].isin(kickoff) & (ecr["scrape_date"] < ecr["season"].map(kickoff))]
# Keep the LAST snapshot before each season's kickoff
ecr = ecr[ecr["scrape_date"] == ecr.groupby("season")["scrape_date"].transform("max")]
ecr["preseason_rank"] = ecr.groupby(["season", "pos"])["ecr"].rank(method="first").astype(int)
ecr["preseason_team"] = ecr["team"].replace(TEAM_FIX)

# FantasyPros id -> gsis id
ids = pd.read_parquet(RAW / "ff_playerids.parquet", columns=["fantasypros_id", "gsis_id"]).dropna()
ids["fantasypros_id"] = ids["fantasypros_id"].astype("int64").astype(str)
ids = ids.drop_duplicates("fantasypros_id")
ecr = ecr.merge(ids, left_on="id", right_on="fantasypros_id", how="inner")
ecr = (ecr.rename(columns={"gsis_id": "player_id", "ecr": "preseason_ecr", "sd": "preseason_ecr_sd"})
       .drop_duplicates(["player_id", "season"])
       [["player_id", "season", "preseason_rank", "preseason_ecr", "preseason_ecr_sd", "preseason_team"]])

# Actual finish: positional rank by total PPR points
box["finish_rank"] = box.groupby(["season", "position"])["ppr"].rank(ascending=False, method="first").astype(int)
box["finish_rank_ppg"] = (box[box["games"] >= 6].groupby(["season", "position"])["ppr_per_game"]
                          .rank(ascending=False, method="first"))


# ===========================================================================
# ASSEMBLE
# ===========================================================================
print("7. Assembling...")
df = (
    box.merge(routes, on=["player_id", "season"], how="left")
    .merge(cov, on=["player_id", "season"], how="left")
    .merge(ngs, on=["player_id", "season"], how="left")
    .merge(opp, on=["player_id", "season"], how="left")
    .merge(bio, on=["player_id", "season"], how="left")
)
df = (df.merge(pfr, left_on=["pfr_id", "season"], right_on=["pfr_player_id", "season"], how="left")
        .drop(columns=["pfr_player_id"]))
df = df.merge(combine, on="pfr_id", how="left")
df = df.merge(team, on=["team", "season"], how="left")
df = df.merge(ecr.drop(columns=["preseason_team"]), on=["player_id", "season"], how="left")

df["xfp_per_game"] = df["xfp"] / df["games"]
df["fp_over_expected_per_game"] = (df["fp_std"] - df["xfp"]) / df["games"]
df = df.drop(columns=["fp_std"])
df["outperformance"] = df["preseason_rank"] - df["finish_rank"]   # + = beat the market

# 6. NEXT SEASON: pair each row with the same player's following season
nxt = box[["player_id", "season", "team", "games", "ppr", "ppr_per_game", "finish_rank"]].copy()
nxt["season"] -= 1
nxt = nxt.add_prefix("next_").rename(columns={"next_player_id": "player_id", "next_season": "season"})
df = df.merge(nxt, on=["player_id", "season"], how="left")

nxt_ecr = ecr.copy()
nxt_ecr["season"] -= 1     # 2026 preseason rank lands on the 2025 row
nxt_ecr = nxt_ecr.rename(columns={"preseason_rank": "next_preseason_rank",
                                  "preseason_ecr": "next_preseason_ecr",
                                  "preseason_ecr_sd": "next_preseason_ecr_sd",
                                  "preseason_team": "next_preseason_team"})
df = df.merge(nxt_ecr, on=["player_id", "season"], how="left")

df["changed_team"] = np.where(df["next_preseason_team"].isna(), np.nan,
                              (df["next_preseason_team"] != df["team"]).astype(float))
df["next_outperformance"] = df["next_preseason_rank"] - df["next_finish_rank"]

# Tidy column order
first = ["player_id", "name", "position", "season", "team", "n_teams", "age", "years_exp",
         "games", "ppr", "ppr_per_game", "finish_rank", "finish_rank_ppg",
         "preseason_rank", "outperformance"]
last = [c for c in df.columns if c.startswith("next_")] + ["changed_team"]
df = df[first + [c for c in df.columns if c not in first + last] + last]
df = df.sort_values(["season", "position", "finish_rank"]).reset_index(drop=True)

df.to_parquet(OUT / "player_seasons.parquet", index=False)
df.round(3).to_csv(OUT / "player_seasons.csv", index=False)
print(f"\nSaved {len(df):,} player-seasons x {df.shape[1]} columns -> {OUT / 'player_seasons.parquet'}")
print(df.groupby("position").size().to_string())
