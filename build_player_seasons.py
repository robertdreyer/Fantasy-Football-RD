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

COORDINATORS = Path("reference/coordinators.csv")   # made by collect_coordinators.py
PLAY_CALLERS = Path("reference/play_callers.csv")   # researched: who called the offensive plays
PRESEASON_QBS = Path("reference/preseason_qbs.csv")  # made by build_qb_seasons.py
QB_RECORDS = OUT / "qb_records.parquet"             # made by build_qb_seasons.py
QB_MIX = OUT / "team_qb_dropbacks.parquet"          # made by build_qb_seasons.py

# Older team codes (FantasyPros, old depth charts) -> nflverse team codes
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
box["run_10plus_rate"] = per(box["runs_10plus"], box["carries"])          # chunk runs
box["yac_per_reception"] = per(box["yac"], box["receptions"])            # yards after the catch


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
            "passer_player_name", "epa", "pass_oe", "cpoe", "yardline_100", "down",
            "air_yards", "rusher_player_id", "week",
            "passing_yards", "pass_touchdown", "rush_touchdown", "success"]
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
ecr["preseason_team"] = ecr["team"].replace(TEAM_FIX).replace({"FA": np.nan})   # FA = unsigned

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
# 6. MORE PLAYER FEATURES: scoring chances, role, consistency, health, scheme
# ===========================================================================
print("7. Red zone, deep targets, consistency, injuries, scheme...")

# --- 6a. Red-zone / end-zone / deep targets and goal-line carries (play-by-play)
tg = pbp[(pbp["play_type"] == "pass") & pbp["receiver_player_id"].notna()].copy()
tg["rz"] = tg["yardline_100"] <= 20
tg["ez"] = tg["air_yards"] >= tg["yardline_100"]          # thrown into the end zone
tg["deep"] = tg["air_yards"] >= 20
ca = pbp[(pbp["rush_attempt"] == 1) & (pbp["qb_scramble"] == 0) & pbp["rusher_player_id"].notna()].copy()
ca["rz"] = ca["yardline_100"] <= 20
ca["gl"] = ca["yardline_100"] <= 5

scoring = pd.concat([
    tg.groupby(["receiver_player_id", "season"])[["rz", "ez", "deep"]].sum()
      .rename(columns={"rz": "rz_targets", "ez": "ez_targets", "deep": "deep_targets"}),
    ca.groupby(["rusher_player_id", "season"])[["rz", "gl"]].sum()
      .rename(columns={"rz": "rz_carries", "gl": "gl_carries"}),
], axis=1).fillna(0)
scoring.index.names = ["player_id", "season"]
scoring = scoring.reset_index()

team_scoring = pd.concat([
    tg.groupby(["posteam", "season"])[["rz", "ez"]].sum().rename(columns={"rz": "t_rz_tgt", "ez": "t_ez_tgt"}),
    ca.groupby(["posteam", "season"])[["rz", "gl"]].sum().rename(columns={"rz": "t_rz_car", "gl": "t_gl_car"}),
], axis=1).reset_index().rename(columns={"posteam": "team"})

# --- 6b. Week-to-week consistency (weekly PPR)
wk = stats[["player_id", "season", "week", "fantasy_points_ppr"]]
consistency = wk.groupby(["player_id", "season"])["fantasy_points_ppr"].agg(
    ppr_weekly_sd="std",
    boom_rate=lambda x: (x >= 20).mean(),     # share of games with 20+ PPR points
    bust_rate=lambda x: (x < 5).mean(),       # share of games under 5
).reset_index()
halves = (wk.assign(half=np.where(wk["week"] <= 9, "first_half_ppg", "second_half_ppg"))
          .groupby(["player_id", "season", "half"])["fantasy_points_ppr"].mean().unstack().reset_index())
halves["second_half_trend"] = halves["second_half_ppg"] - halves["first_half_ppg"]   # + = finished strong
consistency = consistency.merge(halves, on=["player_id", "season"], how="left")

# --- 6c. Health: injury-report history and games missed
inj = pd.read_parquet(RAW / "injuries.parquet")
inj = inj[inj["game_type"] == "REG"].dropna(subset=["gsis_id"])
inj["season"] = inj["season"].astype(int)
soft = inj["report_primary_injury"].fillna("").str.contains("Hamstring|Groin|Calf|Quad", case=False)
health = (inj.assign(out=inj["report_status"] == "Out",
                     dnp=inj["practice_status"].fillna("").str.startswith("Did Not"),
                     soft=soft)
          .groupby(["gsis_id", "season"])[["out", "dnp", "soft"]].sum()
          .rename(columns={"out": "weeks_listed_out", "dnp": "weeks_dnp_practice",
                           "soft": "soft_tissue_reports"})
          .reset_index().rename(columns={"gsis_id": "player_id"}))

# --- 6d. Targets: catchable / contested (FTN charting, 2022+)
ftn = pd.read_parquet(RAW / "ftn_charting.parquet",
                      columns=["nflverse_game_id", "nflverse_play_id", "is_catchable_ball",
                               "is_contested_ball", "is_motion", "is_play_action", "is_screen_pass"])
ftn = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
tg_ftn = tg.merge(ftn, on=["game_id", "play_id"], how="inner")
target_quality = tg_ftn.groupby(["receiver_player_id", "season"]).agg(
    catchable_target_rate=("is_catchable_ball", "mean"),
    contested_target_rate=("is_contested_ball", "mean"),
).reset_index().rename(columns={"receiver_player_id": "player_id"})

# --- 6e. Scheme and protection (team-season)
db_ftn = pbp[pbp["qb_dropback"] == 1].merge(ftn, on=["game_id", "play_id"], how="inner")
scheme = db_ftn.groupby(["posteam", "season"]).agg(
    team_motion_rate=("is_motion", "mean"),
    team_play_action_rate=("is_play_action", "mean"),
    team_screen_rate=("is_screen_pass", "mean"),
).reset_index().rename(columns={"posteam": "team"})
press = pd.read_parquet(RAW / "participation.parquet", columns=["nflverse_game_id", "play_id", "was_pressure"])
press = press.rename(columns={"nflverse_game_id": "game_id"}).dropna(subset=["was_pressure"])
press = pbp[pbp["qb_dropback"] == 1].merge(press, on=["game_id", "play_id"], how="inner")
press = (press.assign(was_pressure=press["was_pressure"].astype(bool))
         .groupby(["posteam", "season"])["was_pressure"].mean()
         .rename("team_pressure_rate_allowed").reset_index().rename(columns={"posteam": "team"}))
team = (team.merge(team_scoring, on=["team", "season"], how="left")
            .merge(scheme, on=["team", "season"], how="left")
            .merge(press, on=["team", "season"], how="left"))


# ===========================================================================
# 7. PRESEASON ROLE: depth chart before each kickoff (incl. 2026), contracts
# ===========================================================================
print("8. Preseason depth charts, vacated targets, contracts...")
# Old format (2016-2024): week-1 chart. depth_team 1 = starter (3 WR starters, 1 RB, 1 TE).
dco = pd.read_parquet(RAW / "depth_charts_weekly.parquet")
dco = dco[(dco["formation"] == "Offense") & dco["position"].isin(POSITIONS) & (dco["game_type"] == "REG")]
dco = dco[dco["week"] == dco.groupby("season")["week"].transform("min")]
dco["depth"] = pd.to_numeric(dco["depth_team"].astype(str).str.strip(), errors="coerce")
dco = dco.rename(columns={"gsis_id": "player_id", "club_code": "depth_team_code"})

# New format (2025+): last snapshot before kickoff. Convert WR rank to the same tiers
# as the old format (WR1-3 = tier 1, WR4-6 = tier 2); RB/TE rank = tier.
dcn = pd.read_parquet(RAW / "depth_charts_daily.parquet")
dcn = dcn[dcn["pos_abb"].isin(POSITIONS) & ~dcn["pos_grp"].str.contains("Special|D$|Defense", regex=True)]
dcn["season"] = dcn["dt"].str[:4].astype(int)
dcn = dcn[dcn["dt"].str[:10] < dcn["season"].map(kickoff)]
dcn = dcn[dcn["dt"] == dcn.groupby("season")["dt"].transform("max")]
dcn["depth"] = np.where(dcn["pos_abb"] == "WR", np.ceil(dcn["pos_rank"] / 3), dcn["pos_rank"])
dcn = dcn.rename(columns={"gsis_id": "player_id", "team": "depth_team_code"})

depth = pd.concat([dco[["player_id", "season", "depth_team_code", "depth"]],
                   dcn[["player_id", "season", "depth_team_code", "depth"]]], ignore_index=True)
depth = depth.dropna(subset=["player_id"])
depth["depth_team_code"] = depth["depth_team_code"].replace(TEAM_FIX)
depth = (depth.sort_values("depth").drop_duplicates(["player_id", "season"])
         .rename(columns={"depth_team_code": "preseason_depth_team", "depth": "preseason_depth_tier"}))

# Preseason team for every player-season: depth chart first, FantasyPros as backup
pre_team = depth[["player_id", "season", "preseason_depth_team"]].merge(
    ecr[["player_id", "season", "preseason_team"]], on=["player_id", "season"], how="outer")
pre_team["preseason_team"] = pre_team["preseason_depth_team"].fillna(pre_team["preseason_team"])
pre_team = pre_team[["player_id", "season", "preseason_team"]]

# Vacated targets/carries: production from team T in season N by players who are
# NOT on T's depth chart (or anywhere) the following preseason.
moves = box[["player_id", "season", "team", "targets", "carries"]].merge(
    pre_team.assign(season=pre_team["season"] - 1).rename(columns={"preseason_team": "next_pre_team"}),
    on=["player_id", "season"], how="left")
moves["left"] = moves["next_pre_team"] != moves["team"]          # includes "no longer on any chart"
vacated = moves.groupby(["team", "season"]).apply(
    lambda g: pd.Series({
        "vacated_target_share": g.loc[g["left"], "targets"].sum() / max(g["targets"].sum(), 1),
        "vacated_carry_share": g.loc[g["left"], "carries"].sum() / max(g["carries"].sum(), 1),
    }), include_groups=False).reset_index()
# Only seasons where next preseason depth charts exist can be measured
vacated = vacated[vacated["season"] + 1 <= 2026]

# Competition on his NEXT team: the share of that team's carries/targets this season
# that belonged to OTHER players who are still on its depth chart next preseason.
# Example: Kenneth Walker shared Seattle's backfield in 2025 (about half the carries),
# then moved to a Kansas City backfield whose returning backs had few carries.
team_tot = box.groupby(["team", "season"])[["carries", "targets"]].sum().rename(
    columns={"carries": "t_car", "targets": "t_tgt"})
retained = (moves[~moves["left"]].groupby(["team", "season"])[["carries", "targets"]].sum()
            .rename(columns={"carries": "kept_car", "targets": "kept_tgt"}))
team_comp = team_tot.join(retained, how="left").fillna(0).reset_index()

# Contracts: the deal in force for the following season (OverTheCap)
con = pd.read_parquet(RAW / "contracts.parquet",
                      columns=["gsis_id", "year_signed", "years", "apy_cap_pct", "guaranteed"])
con = con.dropna(subset=["gsis_id", "year_signed", "years"])
con["last_year"] = con["year_signed"] + con["years"] - 1


def contract_for(season_df):
    """For each (player_id, season) row, the contract covering season + 1."""
    m = season_df[["player_id", "season"]].merge(con, left_on="player_id", right_on="gsis_id")
    target = m["season"] + 1
    m = m[(m["year_signed"] <= target) & (m["last_year"] >= target)]
    m = m.sort_values(["year_signed", "apy_cap_pct"]).drop_duplicates(["player_id", "season"], keep="last")
    return m.assign(next_contract_new=(m["year_signed"] == m["season"] + 1).astype(int))[
        ["player_id", "season", "apy_cap_pct", "guaranteed", "next_contract_new"]].rename(
        columns={"apy_cap_pct": "next_contract_apy_cap_pct", "guaranteed": "next_contract_guaranteed_m"})



# --- Next season's schedule strength: opponents' defense in the season just played.
# (Defenses change a lot year to year, so expect this to be a weak signal.)
defense = pd.concat([
    db.groupby(["defteam", "season"])["epa"].mean().rename("def_epa_per_dropback_allowed"),
    runs.groupby(["defteam", "season"])["epa"].mean().rename("def_epa_per_rush_allowed"),
], axis=1).reset_index().rename(columns={"defteam": "opp"})
sched = pd.concat([pd.read_parquet(RAW / "schedules.parquet").query("game_type == 'REG'"),
                   pd.read_parquet(RAW / "schedule_2026.parquet").query("game_type == 'REG'")])
sched = pd.concat([sched[["season", "home_team", "away_team"]].set_axis(["season", "team", "opp"], axis=1),
                   sched[["season", "away_team", "home_team"]].set_axis(["season", "team", "opp"], axis=1)])
sched["prev_season"] = sched["season"] - 1
sos = (sched.merge(defense.rename(columns={"season": "prev_season"}), on=["opp", "prev_season"])
       .groupby(["team", "season"])[["def_epa_per_dropback_allowed", "def_epa_per_rush_allowed"]].mean()
       .rename(columns={"def_epa_per_dropback_allowed": "next_sos_pass_def_epa",
                        "def_epa_per_rush_allowed": "next_sos_rush_def_epa"})
       .reset_index())
sos["season"] -= 1     # schedule for season N+1 lands on the season-N row

# --- Play-callers: who called the offense, and the style of offense he ran.
# A team-season's "style" is measured from play-by-play; a caller's style is the style of the
# offense he called. For next season we look up the INCOMING caller's most recent style
# (any team, seasons up to and including this one), so nothing from the future is used.
style = pd.concat([
    team.set_index(["team", "season"])[["team_pass_rate_over_exp", "team_dropbacks_per_game"]],
], axis=1)
pos_map = box.drop_duplicates("player_id").set_index("player_id")["position"]
tg_pos = tg.assign(pos=tg["receiver_player_id"].map(pos_map))
tshare = tg_pos.groupby(["posteam", "season"])["pos"].value_counts(normalize=True).unstack(fill_value=0)
top = (tg_pos.groupby(["posteam", "season", "receiver_player_id"]).size()
       .groupby(level=[0, 1]).apply(lambda x: x.max() / x.sum()))
style = style.join(pd.DataFrame({"rb_target_share": tshare.get("RB"), "te_target_share": tshare.get("TE"),
                                 "top_target_share": top}).rename_axis(["team", "season"]), how="left")
style = style.join(scheme.set_index(["team", "season"])[["team_motion_rate", "team_play_action_rate"]], how="left")
style = style.rename(columns={"team_pass_rate_over_exp": "pass_rate_over_exp", "team_dropbacks_per_game": "dropbacks_per_game",
                              "team_motion_rate": "motion_rate", "team_play_action_rate": "play_action_rate"}).reset_index()
STYLE_COLS = ["pass_rate_over_exp", "dropbacks_per_game", "rb_target_share", "te_target_share",
              "top_target_share", "motion_rate", "play_action_rate"]

callers = None
if PLAY_CALLERS.exists():
    callers = pd.read_csv(PLAY_CALLERS)[["season", "team", "play_caller"]].dropna()
    caller_hist = callers.merge(style, on=["team", "season"], how="inner")   # seasons with play-by-play


    def caller_style_before(names_seasons):
        """For each (caller, season S), his most recent style from seasons < S, plus seasons of experience."""
        out = []
        for (name, S) in names_seasons:
            h = caller_hist[(caller_hist["play_caller"] == name) & (caller_hist["season"] < S)]
            if len(h):
                last = h.sort_values("season").iloc[-1]
                out.append({"play_caller": name, "season_called": S, "caller_seasons_before": len(h),
                            **{f"caller_{c}": last[c] for c in STYLE_COLS}})
            else:
                out.append({"play_caller": name, "season_called": S, "caller_seasons_before": 0})
        return pd.DataFrame(out)

# --- Offensive production: how much each offense produced, so a play-caller gets credit (or blame).
# Raw totals drift by era, so each stat is also turned into a z-score within its season
# (0 = league average that year, +1 = one standard deviation better than average).
pts = pd.read_parquet(RAW / "schedules.parquet").query("game_type == 'REG'").dropna(subset=["home_score"])
pts = pd.concat([pts[["season", "home_team", "home_score"]].set_axis(["season", "team", "points"], axis=1),
                 pts[["season", "away_team", "away_score"]].set_axis(["season", "team", "points"], axis=1)])
pts["team"] = pts["team"].replace(TEAM_FIX)
all_fp = pd.read_parquet(RAW / "player_stats_weekly.parquet", columns=["season", "season_type", "team", "fantasy_points_ppr"])
all_fp = all_fp[all_fp["season_type"] == "REG"]
prod = pd.concat([
    pts.groupby(["team", "season"])["points"].mean().rename("off_points_pg"),
    off.groupby(["posteam", "season"])["passing_yards"].sum().rename("pass_yds"),
    off.groupby(["posteam", "season"])["rushing_yards"].sum().rename("rush_yds"),
    off.groupby(["posteam", "season"])["pass_touchdown"].sum().rename("pass_td"),
    off.groupby(["posteam", "season"])["rush_touchdown"].sum().rename("rush_td"),
    off.groupby(["posteam", "season"])["epa"].mean().rename("off_epa_per_play"),
    off.groupby(["posteam", "season"])["success"].mean().rename("off_success_rate"),
    all_fp.groupby(["team", "season"])["fantasy_points_ppr"].sum().rename("fp"),
    games_per_team,
], axis=1).rename_axis(["team", "season"]).reset_index().dropna(subset=["team_games"])
for c in ["pass_yds", "rush_yds", "pass_td", "rush_td", "fp"]:
    prod[f"{c}_pg"] = prod[c] / prod["team_games"]
prod["total_yds_pg"] = prod["pass_yds_pg"] + prod["rush_yds_pg"]
prod["off_td_pg"] = prod["pass_td_pg"] + prod["rush_td_pg"]
prod = prod.rename(columns={"pass_yds_pg": "off_pass_yds_pg", "rush_yds_pg": "off_rush_yds_pg",
                            "pass_td_pg": "off_pass_td_pg", "rush_td_pg": "off_rush_td_pg",
                            "fp_pg": "off_fantasy_pts_pg", "total_yds_pg": "off_total_yds_pg"})
PROD_COLS = ["off_points_pg", "off_total_yds_pg", "off_pass_yds_pg", "off_rush_yds_pg", "off_td_pg",
             "off_pass_td_pg", "off_rush_td_pg", "off_epa_per_play", "off_success_rate", "off_fantasy_pts_pg"]
prod = prod[["team", "season"] + PROD_COLS]
for c in PROD_COLS:
    g = prod.groupby("season")[c]
    prod[f"{c}_z"] = (prod[c] - g.transform("mean")) / g.transform("std")
# One overall production score: average of the points, yards, TD and fantasy z-scores
PROD_Z = ["off_points_pg_z", "off_total_yds_pg_z", "off_td_pg_z", "off_fantasy_pts_pg_z"]
prod["off_production_z"] = prod[PROD_Z].mean(axis=1)

caller_record = None
if callers is not None:
    # Every season a caller ran an offense, with what that offense produced
    caller_seasons = (callers.merge(prod, on=["team", "season"], how="inner")
                      .sort_values(["play_caller", "season"]))
    # "Lift": his offense vs. the same team's offense the year before he arrived (new stints only)
    prev = prod[["team", "season", "off_production_z"]].assign(season=lambda x: x["season"] + 1)
    caller_seasons = caller_seasons.merge(prev.rename(columns={"off_production_z": "team_prev_production_z"}),
                                          on=["team", "season"], how="left")
    prev_caller = callers.assign(season=callers["season"] + 1).rename(columns={"play_caller": "prev_team_caller"})
    caller_seasons = caller_seasons.merge(prev_caller, on=["team", "season"], how="left")
    new_stint = caller_seasons["prev_team_caller"].notna() & (caller_seasons["prev_team_caller"] != caller_seasons["play_caller"])
    caller_seasons["first_year_lift_z"] = np.where(
        new_stint, caller_seasons["off_production_z"] - caller_seasons["team_prev_production_z"], np.nan)
    caller_seasons = caller_seasons.drop(columns=["prev_team_caller"])
    caller_seasons.round(3).to_csv("reference/play_caller_offense.csv", index=False)

    SHRINK = 1   # pretend each caller also had 1 league-average season, so 1 great year doesn't look like 5

    def caller_record_before(names_seasons):
        """Each caller's production track record from seasons BEFORE S (never the season being predicted)."""
        out = []
        for name, S in names_seasons:
            h = caller_seasons[(caller_seasons["play_caller"] == name) & (caller_seasons["season"] < S)]
            n = len(h)
            row = {"play_caller": name, "season_called": S}
            # No history (first-time caller, or first seen before 2016 data): league average, z = 0
            row.update({c: 0.0 for c in ["caller_production_z", "caller_points_z", "caller_pass_yds_z",
                                         "caller_rush_yds_z", "caller_fantasy_z"]})
            if n:
                row.update({
                    "caller_production_z": h["off_production_z"].sum() / (n + SHRINK),
                    "caller_points_z": h["off_points_pg_z"].sum() / (n + SHRINK),
                    "caller_pass_yds_z": h["off_pass_yds_pg_z"].sum() / (n + SHRINK),
                    "caller_rush_yds_z": h["off_rush_yds_pg_z"].sum() / (n + SHRINK),
                    "caller_fantasy_z": h["off_fantasy_pts_pg_z"].sum() / (n + SHRINK),
                    "caller_last_production_z": h["off_production_z"].iloc[-1],
                    "caller_avg_first_year_lift_z": h["first_year_lift_z"].mean(),
                })
            out.append(row)
        return pd.DataFrame(out)

    # Career table for the website / README (all seasons through 2025)
    caller_record = (caller_seasons.groupby("play_caller")
                     .agg(seasons=("season", "size"), first=("season", "min"), last=("season", "max"),
                          teams=("team", lambda t: ", ".join(dict.fromkeys(t))),
                          points_pg=("off_points_pg", "mean"), total_yds_pg=("off_total_yds_pg", "mean"),
                          td_pg=("off_td_pg", "mean"), fantasy_pts_pg=("off_fantasy_pts_pg", "mean"),
                          production_z=("off_production_z", "mean"),
                          avg_first_year_lift_z=("first_year_lift_z", "mean"))
                     .assign(production_z_shrunk=lambda x: x["production_z"] * x["seasons"] / (x["seasons"] + SHRINK))
                     .sort_values("production_z_shrunk", ascending=False).reset_index())
    caller_record.round(3).to_csv("reference/play_caller_track_record.csv", index=False)

# --- Coordinators (optional until reference/coordinators.csv exists)
coords = None
if COORDINATORS.exists() and len(pd.read_csv(COORDINATORS)) > 0:
    coords = pd.read_csv(COORDINATORS)
    for c in ["head_coach", "oc", "dc"]:
        coords[c] = coords[c].fillna("").astype(str).str.split(" / ").str[0].replace("", np.nan)
    coords = coords[["season", "team", "head_coach", "oc", "dc"]]
    # OC tendency travels with the coordinator: his team's pass rate over expected that season
    oc_proe = (coords.merge(team[["team", "season", "team_pass_rate_over_exp"]], on=["team", "season"])
               .dropna(subset=["oc"]).groupby(["oc", "season"])["team_pass_rate_over_exp"].mean()
               .rename("oc_pass_rate_over_exp").reset_index())
else:
    print("   (reference/coordinators.csv missing or empty: OC/DC columns skipped)")


# ===========================================================================
# ASSEMBLE
# ===========================================================================
print("9. Assembling...")
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
df = (df.merge(scoring, on=["player_id", "season"], how="left")
        .merge(consistency, on=["player_id", "season"], how="left")
        .merge(health, on=["player_id", "season"], how="left")
        .merge(target_quality, on=["player_id", "season"], how="left")
        .merge(depth, on=["player_id", "season"], how="left"))
for c in ["rz_targets", "ez_targets", "deep_targets", "rz_carries", "gl_carries",
          "weeks_listed_out", "weeks_dnp_practice", "soft_tissue_reports"]:
    df[c] = df[c].fillna(0)
df["rz_target_share"] = per(df["rz_targets"], df["t_rz_tgt"])
df["ez_target_share"] = per(df["ez_targets"], df["t_ez_tgt"])
df["rz_carry_share"] = per(df["rz_carries"], df["t_rz_car"])
df["gl_carry_share"] = per(df["gl_carries"], df["t_gl_car"])
df["deep_target_rate"] = per(df["deep_targets"], df["targets"])
df["adot"] = per(df["air_yards"], df["targets"])
df = df.drop(columns=["t_rz_tgt", "t_ez_tgt", "t_rz_car", "t_gl_car"])

# Games missed (any reason) this season and the two before it
team_games = pbp.groupby(["posteam", "season"])["game_id"].nunique().rename("team_games_played")
df = df.merge(team_games, left_on=["team", "season"], right_index=True, how="left")
df["games_missed"] = (df["team_games_played"] - df["games"]).clip(lower=0)
gm = df[["player_id", "season", "games_missed"]]
for lag in (1, 2):
    df = df.merge(gm.assign(season=gm["season"] + lag)
                    .rename(columns={"games_missed": f"games_missed_prev{lag}"}),
                  on=["player_id", "season"], how="left")
df["games_missed_last3"] = df[["games_missed", "games_missed_prev1", "games_missed_prev2"]].sum(axis=1, min_count=1)
df = df.drop(columns=["team_games_played", "games_missed_prev1", "games_missed_prev2"])

if coords is not None:
    df = df.merge(coords, on=["team", "season"], how="left")

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

df = df.copy()   # defragment after many merges
# Next preseason team: depth chart first, FantasyPros second
nxt_team = pre_team.assign(season=pre_team["season"] - 1).rename(columns={"preseason_team": "nt"})
nxt_depth = depth.assign(season=depth["season"] - 1)[["player_id", "season", "preseason_depth_tier"]] \
                 .rename(columns={"preseason_depth_tier": "next_preseason_depth_tier"})
df = df.merge(nxt_team, on=["player_id", "season"], how="left").merge(nxt_depth, on=["player_id", "season"], how="left")
df["next_preseason_team"] = df["nt"].fillna(df["next_preseason_team"])
df = df.drop(columns=["nt"])
df["changed_team"] = np.where(df["next_preseason_team"].isna(), np.nan,
                              (df["next_preseason_team"] != df["team"]).astype(float))

# Opportunity waiting on his NEXT team
df = df.merge(vacated.rename(columns={"team": "next_preseason_team",
                                      "vacated_target_share": "next_team_vacated_target_share",
                                      "vacated_carry_share": "next_team_vacated_carry_share"}),
              on=["next_preseason_team", "season"], how="left")
df = df.merge(contract_for(df), on=["player_id", "season"], how="left")
# Own share of his team's carries/targets this season (players at WR/TE/RB)
df = df.merge(team_tot.reset_index(), on=["team", "season"], how="left")
df["team_carry_share"] = per(df["carries"], df["t_car"])
df["team_target_share_season"] = per(df["targets"], df["t_tgt"])
df = df.drop(columns=["t_car", "t_tgt"])

# Competition waiting on his next team (his own numbers excluded if he stays)
nc = team_comp.rename(columns={"team": "next_preseason_team"})
df = df.merge(nc, on=["next_preseason_team", "season"], how="left")
stays = df["next_preseason_team"] == df["team"]
kept_car = df["kept_car"] - np.where(stays, df["carries"], 0)
kept_tgt = df["kept_tgt"] - np.where(stays, df["targets"], 0)
df["next_competition_carry_share"] = per(kept_car.clip(lower=0), df["t_car"])
df["next_competition_target_share"] = per(kept_tgt.clip(lower=0), df["t_tgt"])
# Room to grow: work NOT held by returning teammates, minus what he already had
df["carry_share_gap"] = (1 - df["next_competition_carry_share"]) - df["team_carry_share"]
# Carries per game left over on his next team after returning teammates take their share,
# compared with what he got this season (+ = room for a bigger workload)
games_pg = pbp.groupby(["posteam", "season"])["game_id"].nunique()
df["next_team_games"] = [games_pg.get((t, s), np.nan) for t, s in zip(df["next_preseason_team"], df["season"])]
df["open_carries_per_game"] = (df["t_car"] - kept_car.clip(lower=0)) / df["next_team_games"]
df["open_carries_vs_current"] = df["open_carries_per_game"] - df["carries_per_game"]
df["open_targets_per_game"] = (df["t_tgt"] - kept_tgt.clip(lower=0)) / df["next_team_games"]
df["open_targets_vs_current"] = df["open_targets_per_game"] - df["targets_per_game"]
df = df.drop(columns=["next_team_games"])
df["target_share_gap"] = (1 - df["next_competition_target_share"]) - df["team_target_share_season"]
df = df.drop(columns=["t_car", "t_tgt", "kept_car", "kept_tgt"])
# Higher = easier schedule (opponents allowed more EPA last year)
df = df.merge(sos.rename(columns={"team": "next_preseason_team"}), on=["next_preseason_team", "season"], how="left")

if callers is not None:
    # This season's caller for his team, and next season's caller for his next team
    df = df.merge(callers.rename(columns={"play_caller": "play_caller"}), on=["team", "season"], how="left")
    nxt_c = callers.assign(season=callers["season"] - 1).rename(
        columns={"team": "next_preseason_team", "play_caller": "next_play_caller"})
    df = df.merge(nxt_c, on=["next_preseason_team", "season"], how="left")
    df["play_caller_changed"] = np.where(df["play_caller"].isna() | df["next_play_caller"].isna(), np.nan,
                                         (df["play_caller"] != df["next_play_caller"]).astype(float))
    pairs = df.loc[df["next_play_caller"].notna(), ["next_play_caller", "season"]].drop_duplicates()
    hist = caller_style_before([(n, s + 1) for n, s in pairs.itertuples(index=False)])
    hist = hist.rename(columns={"play_caller": "next_play_caller"}).assign(season=lambda x: x["season_called"] - 1)
    hist = hist.drop(columns=["season_called"]).add_prefix("next_").rename(
        columns={"next_next_play_caller": "next_play_caller", "next_season": "season"})
    df = df.merge(hist, on=["next_play_caller", "season"], how="left")
    df["next_caller_first_time"] = np.where(df["next_play_caller"].isna(), np.nan,
                                            (df["next_caller_seasons_before"] == 0).astype(float))
    # How different the incoming caller's style is from what his team ran this season
    cur = style.rename(columns={c: f"cur_{c}" for c in STYLE_COLS})
    df = df.merge(cur, on=["team", "season"], how="left")
    for c in ["pass_rate_over_exp", "rb_target_share", "te_target_share", "top_target_share"]:
        df[f"next_caller_{c}_shift"] = df[f"next_caller_{c}"] - df[f"cur_{c}"]
    df = df.drop(columns=[f"cur_{c}" for c in STYLE_COLS])

    # The offense he plays in this season, and the incoming caller's production track record
    df = df.merge(prod[["team", "season", "off_points_pg", "off_total_yds_pg", "off_td_pg",
                        "off_fantasy_pts_pg", "off_production_z"]], on=["team", "season"], how="left")
    rec = caller_record_before([(n, s + 1) for n, s in pairs.itertuples(index=False)])
    rec = (rec.rename(columns={"play_caller": "next_play_caller"})
              .assign(season=lambda x: x["season_called"] - 1).drop(columns=["season_called"]))
    rec = rec.rename(columns={c: f"next_{c}" for c in rec.columns if c.startswith("caller_")})
    df = df.merge(rec, on=["next_play_caller", "season"], how="left")
    # + = he's moving to (or getting) a caller whose offenses produced more than his current one
    df["next_caller_production_vs_current"] = df["next_caller_production_z"] - df["off_production_z"]

# --- Quarterbacks: next season's projected starter vs. the QB play he had this season.
# Both sides are measured the same way: track records entering next season (earlier seasons only).
# "This season" blends every QB who threw for his team, weighted by dropbacks, so a star returning
# from injury (Burrow after a Flacco year) shows up as an upgrade.
QB_REC_COLS = ["qb_rec_epa_per_dropback", "qb_rec_cpoe", "qb_rec_any_a", "qb_rec_fantasy_ppg",
               "qb_rec_qb_rush_share", "qb_rec_qb_goal_line_share", "qb_rec_deep_attempt_rate",
               "qb_rec_rb_target_share", "qb_rec_te_target_share", "qb_rec_top_target_share"]
if PRESEASON_QBS.exists() and QB_RECORDS.exists() and QB_MIX.exists():
    pq = pd.read_csv(PRESEASON_QBS)
    qrec = pd.read_parquet(QB_RECORDS)
    # Next season's projected starter for his next team
    nq = (pq[["season", "team", "qb_id", "qb_name"]]
          .assign(season=lambda x: x["season"] - 1)
          .rename(columns={"team": "next_preseason_team", "qb_id": "next_qb_id", "qb_name": "next_qb_name"}))
    df = df.merge(nq, on=["next_preseason_team", "season"], how="left")
    nr = (qrec[["player_id", "season", "qb_starts_before"] + QB_REC_COLS]
          .assign(season=lambda x: x["season"] - 1)
          .rename(columns={"player_id": "next_qb_id", "qb_starts_before": "next_qb_starts_before",
                           **{c: f"next_{c}" for c in QB_REC_COLS}}))
    df = df.merge(nr, on=["next_qb_id", "season"], how="left")
    # The QB who threw the most for his team this season, with his record entering next season
    cq = pq[["season", "team", "actual_main_qb_id"]].rename(columns={"actual_main_qb_id": "cur_qb_id"})
    df = df.merge(cq, on=["team", "season"], how="left")
    mixq = pd.read_parquet(QB_MIX).merge(
        qrec[["player_id", "season"] + QB_REC_COLS].assign(season=lambda x: x["season"] - 1),
        on=["player_id", "season"], how="left")
    def blend(g):
        """Dropback-weighted average of each record over the QBs who threw for the team."""
        out = {}
        for c in QB_REC_COLS:
            ok = g[c].notna()
            out[f"cur_{c}"] = np.average(g.loc[ok, c], weights=g.loc[ok, "dropback_share"]) if ok.any() else np.nan
        return pd.Series(out)

    cur_blend = mixq.groupby(["team", "season"]).apply(blend, include_groups=False).reset_index()
    df = df.merge(cur_blend, on=["team", "season"], how="left")
    df["next_qb_changed"] = np.where(df["next_qb_id"].isna() | df["cur_qb_id"].isna(), np.nan,
                                     (df["next_qb_id"] != df["cur_qb_id"]).astype(float))
    for c in QB_REC_COLS:
        df[f"next_qb_{c.replace('qb_rec_', '')}_shift"] = df[f"next_{c}"] - df[f"cur_{c}"]
    df = df.drop(columns=[f"cur_{c}" for c in QB_REC_COLS])
else:
    print("   (run build_qb_seasons.py first for next-season QB columns)")

if coords is not None:
    nc = coords.assign(season=coords["season"] - 1).rename(
        columns={"team": "next_preseason_team", "head_coach": "next_head_coach", "oc": "next_oc", "dc": "next_dc"})
    df = df.merge(nc, on=["next_preseason_team", "season"], how="left")
    df["oc_changed"] = np.where(df["next_oc"].isna() | df["oc"].isna(), np.nan,
                                (df["next_oc"] != df["oc"]).astype(float))
    # The incoming OC's pass rate over expected in his most recent season (any team)
    df = df.merge(oc_proe.rename(columns={"oc": "next_oc", "oc_pass_rate_over_exp": "next_oc_prior_pass_rate_over_exp"}),
                  on=["next_oc", "season"], how="left")
df["next_outperformance"] = df["next_preseason_rank"] - df["next_finish_rank"]

# Tidy column order
first = ["player_id", "name", "position", "season", "team", "n_teams", "age", "years_exp",
         "games", "ppr", "ppr_per_game", "finish_rank", "finish_rank_ppg",
         "preseason_rank", "outperformance"]
last = [c for c in df.columns if c.startswith("next_")] + \
       [c for c in ["changed_team", "oc_changed"] if c in df.columns]
df = df[first + [c for c in df.columns if c not in first + last] + last]
df = df.sort_values(["season", "position", "finish_rank"]).reset_index(drop=True)

df.to_parquet(OUT / "player_seasons.parquet", index=False)
df.round(3).to_csv(OUT / "player_seasons.csv", index=False)
print(f"\nSaved {len(df):,} player-seasons x {df.shape[1]} columns -> {OUT / 'player_seasons.parquet'}")
print(df.groupby("position").size().to_string())
