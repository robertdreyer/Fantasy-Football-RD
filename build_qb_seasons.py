"""
build_qb_seasons.py
Step 2a: quarterback history, the projected starter for every team-season, and each QB's track record.

Outputs
  data/processed/qb_seasons.parquet (+ .csv)   one row per QB per regular season, 1999-2025
  data/processed/team_qb_dropbacks.parquet     each QB's share of his team's dropbacks, 2016-2025
  reference/preseason_qbs.csv                  projected starting QB (depth chart before Week 1)
                                               for every team, 2016-2026, next to who actually
                                               threw the most passes that season
  data/processed/qb_records.parquet            each QB's track record entering each season
                                               2016-2026, built ONLY from earlier seasons

Track record = recent seasons count more (each season back is worth 60% of the one after it), and
QBs with few dropbacks are pulled toward a starting point: what QBs drafted in the same range
(1st round / 2nd-3rd / later or undrafted) did in their first seasons. So a rookie or a backup
gets a sensible estimate instead of a blank or one lucky game.

Run it:  python collect_qb_data.py (once)   then   python build_qb_seasons.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)
REF = Path("reference")

LAST_SEASON = 2025
KICKOFF_2026 = "2026-09-09"
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "OAK": "LV", "SD": "LAC", "STL": "LA"}
DECAY = 0.6          # weight of a season relative to the one after it
PRIOR_DROPBACKS = 400  # how many dropbacks of "starting point" each record is blended with


def per(num, den):
    return np.where(den > 0, num / den.replace(0, np.nan), np.nan)


# ===========================================================================
# 1. QB box scores by season, 1999-2025
# ===========================================================================
print("1. QB seasons 1999-2025...")
cols = ["player_id", "player_display_name", "position", "season", "week", "season_type", "team",
        "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
        "sacks_suffered", "sack_yards_lost", "passing_air_yards", "passing_epa", "passing_cpoe",
        "passing_first_downs", "passing_20", "carries", "rushing_yards", "rushing_tds", "rushing_epa",
        "rushing_fumbles_lost", "sack_fumbles_lost", "fantasy_points", "fantasy_points_ppr"]
new = pd.read_parquet(RAW / "player_stats_weekly.parquet", columns=cols)
old = pd.read_parquet(RAW / "qb_stats_weekly_1999_2015.parquet", columns=cols)
wk = pd.concat([old, new[new["position"] == "QB"]], ignore_index=True)
wk = wk[(wk["season_type"] == "REG") & (wk["season"] <= LAST_SEASON)]
wk["team"] = wk["team"].replace(TEAM_FIX)
wk["dropbacks"] = wk["attempts"] + wk["sacks_suffered"]
wk["cpoe_x_att"] = wk["passing_cpoe"] * wk["attempts"]      # weekly CPOE -> attempt-weighted season CPOE
wk["cpoe_att"] = np.where(wk["passing_cpoe"].notna(), wk["attempts"], 0)

# Starter each team-week = the QB with the most dropbacks
wk = wk.sort_values("dropbacks", ascending=False)
wk["started"] = (~wk.duplicated(["season", "week", "team"]) & (wk["dropbacks"] >= 10)).astype(int)

sums = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
        "sack_yards_lost", "passing_air_yards", "passing_epa", "passing_first_downs", "passing_20",
        "carries", "rushing_yards", "rushing_tds", "rushing_epa", "rushing_fumbles_lost", "sack_fumbles_lost",
        "fantasy_points", "fantasy_points_ppr", "dropbacks", "started"]
active = wk[(wk["dropbacks"] > 0) | (wk["carries"] > 0)]
qb = (active.groupby(["player_id", "season"])
      .agg(name=("player_display_name", "last"),
           team=("team", lambda t: t.mode().iloc[0] if t.notna().any() else np.nan),
           games=("week", "nunique"),
           cpoe_x_att=("cpoe_x_att", "sum"),
           cpoe_att=("cpoe_att", "sum"),
           **{c: (c, "sum") for c in sums})
      .reset_index().rename(columns={"started": "starts"}))
qb["epa_per_dropback"] = per(qb["passing_epa"], qb["dropbacks"])
qb["cpoe"] = per(qb["cpoe_x_att"], qb["cpoe_att"])                 # 2006+ (CPOE needs air yards)
qb["any_a"] = per(qb["passing_yards"] + 20 * qb["passing_tds"] - 45 * qb["passing_interceptions"]
                  - qb["sack_yards_lost"], qb["dropbacks"])        # adjusted net yards per attempt
qb["comp_pct"] = per(qb["completions"], qb["attempts"])
qb["td_rate"] = per(qb["passing_tds"], qb["attempts"])
qb["int_rate"] = per(qb["passing_interceptions"], qb["attempts"])
qb["sack_rate"] = per(qb["sacks_suffered"], qb["dropbacks"])
qb["adot"] = per(qb["passing_air_yards"], qb["attempts"])
qb["pass_yds_per_game"] = qb["passing_yards"] / qb["games"]
qb["rush_yds_per_game"] = qb["rushing_yards"] / qb["games"]
qb["carries_per_game"] = qb["carries"] / qb["games"]
qb["fantasy_ppg"] = qb["fantasy_points"] / qb["games"]             # standard QB scoring (4-pt pass TD)
qb = qb.drop(columns=["cpoe_x_att", "cpoe_att"])

# Draft capital and age (rosters 2016+, draft picks for everyone)
draft = pd.read_parquet(RAW / "draft_picks.parquet", columns=["season", "round", "pick", "gsis_id"])
draft = (draft.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")
         .rename(columns={"gsis_id": "player_id", "season": "draft_year", "round": "draft_round",
                          "pick": "draft_pick"}))
qb = qb.merge(draft, on="player_id", how="left")
qb["draft_group"] = np.select([qb["draft_round"] == 1, qb["draft_round"].isin([2, 3])],
                              ["round 1", "rounds 2-3"], "later/undrafted")
births = (pd.read_parquet(RAW / "rosters.parquet", columns=["gsis_id", "birth_date"])
          .dropna().drop_duplicates("gsis_id").rename(columns={"gsis_id": "player_id"}))
qb = qb.merge(births, on="player_id", how="left")
qb["age"] = qb["season"] - pd.to_datetime(qb["birth_date"]).dt.year
qb = qb.drop(columns=["birth_date"])

# ===========================================================================
# 2. Style and pressure, 2016-2025 (play-by-play, Next Gen Stats, PFR)
# ===========================================================================
print("2. QB style from play-by-play (2016+)...")
pcols = ["season", "season_type", "posteam", "play_type", "qb_dropback", "qb_scramble", "rush_attempt",
         "two_point_attempt", "passer_player_id", "rusher_player_id", "receiver_player_id", "air_yards",
         "yardline_100", "pass_attempt"]
pbp = pd.concat([pd.read_parquet(RAW / f"pbp_{s}.parquet", columns=pcols) for s in range(2016, LAST_SEASON + 1)])
pbp = pbp[(pbp["season_type"] == "REG") & (pbp["two_point_attempt"] == 0)]
qb_ids = set(qb["player_id"])
pos = (pd.read_parquet(RAW / "player_stats_weekly.parquet", columns=["player_id", "position"])
       .drop_duplicates("player_id").set_index("player_id")["position"])

rushes = pbp[pbp["rush_attempt"] == 1]
team_rush = rushes.groupby(["posteam", "season"]).size().rename("team_rushes")
qb_runs = rushes[rushes["rusher_player_id"].isin(qb_ids)]
designed = (qb_runs[qb_runs["qb_scramble"] == 0].groupby(["rusher_player_id", "season", "posteam"]).size()
            .rename("designed_runs"))
scr = (qb_runs[qb_runs["qb_scramble"] == 1].groupby(["rusher_player_id", "season", "posteam"]).size()
       .rename("scrambles"))
gl = (qb_runs[qb_runs["yardline_100"] <= 5].groupby(["rusher_player_id", "season", "posteam"]).size()
      .rename("goal_line_runs"))
runs_df = pd.concat([designed, scr, gl], axis=1).fillna(0).reset_index()
runs_df.columns = ["player_id", "season", "team", "designed_runs", "scrambles", "goal_line_runs"]
runs_df = runs_df.merge(team_rush.rename_axis(["team", "season"]).reset_index(), on=["team", "season"])
team_gl = (rushes[rushes["yardline_100"] <= 5].groupby(["posteam", "season"]).size()
           .rename("team_gl_runs").rename_axis(["team", "season"]).reset_index())
runs_df = runs_df.merge(team_gl, on=["team", "season"], how="left")
runs_df = (runs_df.groupby(["player_id", "season"])
           [["designed_runs", "scrambles", "goal_line_runs", "team_rushes", "team_gl_runs"]].sum().reset_index())

passes = pbp[(pbp["pass_attempt"] == 1) & pbp["passer_player_id"].notna()].copy()
passes["tpos"] = passes["receiver_player_id"].map(pos)
passes["deep"] = passes["air_yards"] >= 20
g = passes.groupby(["passer_player_id", "season"])
targets = passes.dropna(subset=["receiver_player_id"])
tshare = targets.groupby(["passer_player_id", "season"])["tpos"].value_counts(normalize=True).unstack(fill_value=0)
top = (targets.groupby(["passer_player_id", "season", "receiver_player_id"]).size()
       .groupby(level=[0, 1]).apply(lambda x: x.nlargest(1).sum() / x.sum()))
style = pd.DataFrame({
    "deep_attempt_rate": g["deep"].mean(),
    "rb_target_share": tshare.get("RB"), "te_target_share": tshare.get("TE"), "wr_target_share": tshare.get("WR"),
    "top_target_share": top,
}).rename_axis(["player_id", "season"]).reset_index()

ngs = pd.read_parquet(RAW / "ngs_passing.parquet")
ngs = (ngs[(ngs["week"] == 0) & (ngs["season_type"] == "REG")]
       [["player_gsis_id", "season", "avg_time_to_throw", "aggressiveness", "avg_air_yards_differential"]]
       .rename(columns={"player_gsis_id": "player_id"}))
pfr = pd.read_parquet(RAW / "pfr_adv_pass.parquet",
                      columns=["pfr_id", "season", "pressure_pct", "bad_throw_pct", "on_tgt_pct", "pocket_time"])
ids = (pd.read_parquet(RAW / "ff_playerids.parquet", columns=["pfr_id", "gsis_id"]).dropna()
       .drop_duplicates("pfr_id").rename(columns={"gsis_id": "player_id"}))
pfr = pfr.merge(ids, on="pfr_id", how="inner").drop(columns=["pfr_id"])

qb = (qb.merge(runs_df, on=["player_id", "season"], how="left")
        .merge(style, on=["player_id", "season"], how="left")
        .merge(ngs, on=["player_id", "season"], how="left")
        .merge(pfr, on=["player_id", "season"], how="left"))
modern = qb["season"] >= 2016
for c in ["designed_runs", "scrambles", "goal_line_runs"]:
    qb.loc[modern, c] = qb.loc[modern, c].fillna(0)
# Share of his team's runs he took himself (designed runs + scrambles): high = fewer carries for RBs
qb["qb_rush_share"] = per(qb["designed_runs"] + qb["scrambles"], qb["team_rushes"])
qb["qb_goal_line_share"] = per(qb["goal_line_runs"], qb["team_gl_runs"])
qb["scramble_rate"] = per(qb["scrambles"], qb["dropbacks"] + qb["scrambles"])
qb = qb.drop(columns=["team_rushes", "team_gl_runs"])
qb = qb.sort_values(["season", "dropbacks"], ascending=[True, False]).reset_index(drop=True)
qb.to_parquet(OUT / "qb_seasons.parquet", index=False)
qb.round(4).to_csv(OUT / "qb_seasons.csv", index=False)
print(f"   {len(qb):,} QB-seasons, {qb['player_id'].nunique():,} QBs")

# ===========================================================================
# 3. Projected starter before each season, 2016-2026
# ===========================================================================
print("3. Preseason starting QBs from depth charts...")
wdc = pd.read_parquet(RAW / "depth_charts_weekly.parquet")
wdc = wdc[(wdc["game_type"] == "REG") & (wdc["formation"] == "Offense") & (wdc["position"] == "QB")
          & (wdc["depth_team"].astype(str) == "1")].copy()
wdc["team"] = wdc["club_code"].replace(TEAM_FIX)
wdc = wdc[wdc["week"] == wdc.groupby(["season", "team"])["week"].transform("min")]   # Week 1 chart
pre = (wdc.drop_duplicates(["season", "team"])[["season", "team", "gsis_id", "full_name"]]
       .assign(source="weekly depth chart, Week 1"))

ddc = pd.read_parquet(RAW / "depth_charts_daily.parquet")
ddc = ddc[(ddc["pos_abb"] == "QB") & (ddc["pos_rank"] == 1)].copy()
sched = pd.read_parquet(RAW / "schedules.parquet")
kick = {2025: str(sched.loc[(sched["season"] == 2025) & (sched["game_type"] == "REG"), "gameday"].min()),
        2026: KICKOFF_2026}
for season, k in kick.items():
    snap = ddc[ddc["dt"] < k]
    snap = snap[snap["dt"] == snap.groupby("team")["dt"].transform("max")]    # last chart before kickoff
    pre = pd.concat([pre, snap.drop_duplicates("team").assign(season=season, source=f"daily depth chart, {k[:10]} kickoff")
                     [["season", "team", "gsis_id", "player_name", "source"]].rename(columns={"player_name": "full_name"})])
pre = pre.rename(columns={"gsis_id": "qb_id", "full_name": "qb_name"})
pre["team"] = pre["team"].replace(TEAM_FIX)

# Every QB's share of his team's dropbacks each season (a QB traded mid-season counts for each team)
mix = (wk[wk["dropbacks"] > 0].groupby(["season", "team", "player_id"])
       .agg(name=("player_display_name", "last"), dropbacks=("dropbacks", "sum")).reset_index())
mix = mix[mix["season"] >= 2016]
mix["dropback_share"] = mix["dropbacks"] / mix.groupby(["season", "team"])["dropbacks"].transform("sum")
mix.to_parquet(OUT / "team_qb_dropbacks.parquet", index=False)
# Who actually threw the most for that team (for the record; 2026 is unknown on purpose)
main = (mix.sort_values("dropbacks", ascending=False)
        .drop_duplicates(["season", "team"])[["season", "team", "player_id", "name"]]
        .rename(columns={"player_id": "actual_main_qb_id", "name": "actual_main_qb"}))
pre = pre.merge(main, on=["season", "team"], how="left").sort_values(["season", "team"])
pre["projected_starter_was_main_qb"] = np.where(pre["actual_main_qb_id"].isna(), np.nan,
                                                (pre["qb_id"] == pre["actual_main_qb_id"]).astype(float))
pre.to_csv(REF / "preseason_qbs.csv", index=False)
print(f"   {len(pre)} team-seasons; projected starter was the main QB in "
      f"{pre['projected_starter_was_main_qb'].mean():.0%} of 2016-2025 team-seasons")

# ===========================================================================
# 4. Track record entering each season (only earlier seasons are used)
# ===========================================================================
print("4. QB track records entering 2016-2026...")
REC_STATS = ["epa_per_dropback", "cpoe", "any_a", "adot", "sack_rate"]       # weighted by dropbacks
PER_GAME = ["fantasy_ppg", "rush_yds_per_game", "pass_yds_per_game"]          # weighted by games
STYLE = ["qb_rush_share", "qb_goal_line_share", "scramble_rate", "deep_attempt_rate",
         "rb_target_share", "te_target_share", "top_target_share"]            # 2016+, weighted by dropbacks


def starting_points(S):
    """What QBs did in their first two seasons, by draft range, using seasons before S only."""
    h = qb[(qb["season"] < S) & (qb["dropbacks"] >= 50)].copy()
    h["yr"] = h["season"] - h.groupby("player_id")["season"].transform("min")
    early = h[h["yr"] <= 1]
    out = {}
    for grp, x in early.groupby("draft_group"):
        out[grp] = {c: np.average(x[c].dropna(), weights=x.loc[x[c].notna(), "dropbacks"]) if x[c].notna().any()
                    else np.nan for c in REC_STATS}
        out[grp].update({c: np.average(x[c], weights=x["games"]) for c in PER_GAME})
    return out


needed = pd.concat([
    pre[["qb_id", "season"]].rename(columns={"qb_id": "player_id"}),
    mix.assign(season=mix["season"] + 1)[["player_id", "season"]],
]).dropna().drop_duplicates()
group_of = qb.drop_duplicates("player_id").set_index("player_id")["draft_group"]
recs = []
for S, ids_S in needed.groupby("season")["player_id"]:
    prior = starting_points(S)
    hist = qb[qb["season"] < S]
    for pid in ids_S:
        h = hist[hist["player_id"] == pid]
        grp = group_of.get(pid, "later/undrafted")
        p = prior.get(grp, prior["later/undrafted"])
        w = DECAY ** (S - 1 - h["season"])
        row = {"player_id": pid, "season": S, "qb_draft_group": grp,
               "qb_seasons_before": len(h[h["dropbacks"] >= 50]), "qb_starts_before": int(h["starts"].sum()),
               "qb_dropbacks_before": int(h["dropbacks"].sum()),
               "qb_seasons_since_last_start": (S - h.loc[h["starts"] > 0, "season"].max()) if (h["starts"] > 0).any() else np.nan}
        for c in REC_STATS:
            ok = h[c].notna()
            wd = (w[ok] * h.loc[ok, "dropbacks"]).sum()
            num = (w[ok] * h.loc[ok, "dropbacks"] * h.loc[ok, c]).sum()
            row[f"qb_rec_{c}"] = (num + PRIOR_DROPBACKS * p[c]) / (wd + PRIOR_DROPBACKS) if pd.notna(p[c]) else np.nan
        for c in PER_GAME:
            wg = (w * h["games"]).sum()
            row[f"qb_rec_{c}"] = ((w * h["games"] * h[c]).sum() + 6 * p[c]) / (wg + 6)   # 6 games of starting point
        for c in STYLE:                                                              # tendencies: no shrinking
            ok = h[c].notna() & (h["dropbacks"] >= 50)
            row[f"qb_rec_{c}"] = (np.average(h.loc[ok, c], weights=(w[ok] * h.loc[ok, "dropbacks"]))
                                  if ok.any() else np.nan)
        recs.append(row)
recs = pd.DataFrame(recs)
recs.to_parquet(OUT / "qb_records.parquet", index=False)
print(f"   {len(recs):,} QB track records")

check = pre[pre["season"] == 2026].merge(recs, left_on=["qb_id", "season"], right_on=["player_id", "season"])
print("\n2026 projected starters, best and worst track records (EPA per dropback):")
show = check.sort_values("qb_rec_epa_per_dropback", ascending=False)[["team", "qb_name", "qb_starts_before",
                                                                       "qb_rec_epa_per_dropback", "qb_rec_cpoe"]]
print(pd.concat([show.head(6), show.tail(6)]).round(3).to_string(index=False))
