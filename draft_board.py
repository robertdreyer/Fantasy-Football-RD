"""
draft_board.py
The 2026 draft board: ESPN's final preseason PPR Top 300 (the order ESPN draft rooms use; cheat sheet
last updated Sept. 8, 2026, the day before kickoff), with the model's view of each WR, RB and TE and
the FantasyPros expert consensus alongside for comparison.

For each position, the model re-ranks the same players ESPN ranked (top 60 WR / 40 RB / 20 TE) by
predicted 2026 PPG. Verdict:
    Value  = the model ranks him at least 10% of the group higher than ESPN (6 WR / 4 RB / 2 TE spots)
    Reach  = the model ranks him at least that much lower
    Fair   = in between
Track record: how often the same verdict, in the same part of the draft, beat its expert rank in the
2020-2025 backtest (market_test.py). That backtest was run against FantasyPros consensus rankings,
because no free archive of past ESPN rankings exists, so for ESPN it is a guide, not a direct test.

QBs, rookies and players outside the tested groups are listed with the rankings only.
Uses the FIRST saved 2026 predictions (predictions/archive), so the board can't change after the fact.

Inputs : reference/espn_2026_ppr_top300.csv  (made by parse_espn_cheatsheet.py from ESPN's PDF)
         data/raw/ecr_rankings.parquet        (FantasyPros, via collect_data.py)
Output : predictions/2026_draft_board.csv     (committed; the website reads it)
Run it : python market_test.py   then   python draft_board.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw")
PRED = Path("predictions")
ESPN = Path("reference/espn_2026_ppr_top300.csv")
KICKOFF_2026 = "2026-09-09"
GROUP = {"WR": 60, "RB": 40, "TE": 20}
POSITIONS = ["WR", "RB", "TE", "QB"]          # kickers and defenses left off
TIERS = ["early picks", "middle picks", "late picks"]


def verdicts(df, rank_col="market_rank", model_col="model_rank", pos_col="position"):
    k = df[pos_col].map(GROUP) * 0.10
    dis = df[rank_col] - df[model_col]
    return np.select([dis >= k, dis <= -k], ["Value", "Reach"], "Fair"), dis


def norm(name):
    """'Kenneth Walker III' -> 'kenneth walker', 'A.J. Brown' -> 'aj brown'"""
    n = re.sub(r"[.'’]", "", str(name).lower())
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)


ALIASES = {"kenny gainwell": "kenneth gainwell", "chig okonkwo": "chigoziem okonkwo"}   # ESPN nickname -> ID map


TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "JAX": "JAX", "GBP": "GB", "KCC": "KC", "LVR": "LV", "NOS": "NO",
            "NEP": "NE", "SFO": "SF", "TBB": "TB", "WSH": "WAS"}
ids = pd.read_parquet(RAW / "ff_playerids.parquet",
                      columns=["fantasypros_id", "gsis_id", "name", "position", "team", "db_season"])
ids = ids.dropna(subset=["gsis_id"])

# --- ESPN: final preseason PPR Top 300
espn = pd.read_csv(ESPN)
espn = espn[espn["pos"].isin(POSITIONS)].copy()
espn["key"] = espn["player"].map(norm)
espn["team"] = espn["team"].replace(TEAM_FIX)
lookup = ids.assign(key=ids["name"].map(norm), team=ids["team"].replace(TEAM_FIX))
m = espn.merge(lookup[["key", "position", "team", "gsis_id"]].rename(columns={"position": "pos"}),
               on=["key", "pos"], how="left", suffixes=("", "_id"))
# Same name and position more than once: prefer the one on the same team
m["same_team"] = (m["team"] == m["team_id"]).astype(int)
m = m.sort_values(["espn_rank", "same_team"], ascending=[True, False]).drop_duplicates("espn_rank")
unmatched = m[m["gsis_id"].isna()]
if len(unmatched):
    print("No ID match (shown with ESPN rank only):", ", ".join(unmatched["player"]))

# --- FantasyPros: overall PPR consensus, last scrape before kickoff (for comparison)
ecr = pd.read_parquet(RAW / "ecr_rankings.parquet")
ecr = ecr[ecr["fp_page"].str.contains(r"(?:^|/)ppr-cheatsheets") & ecr["scrape_date"].between("2026-01-01", KICKOFF_2026)
          & (ecr["scrape_date"] < KICKOFF_2026)]
ecr = ecr[ecr["scrape_date"] == ecr["scrape_date"].max()].copy()
ecr["pos"] = ecr["pos"].str.extract(r"^([A-Z]+)")[0]
ecr = ecr[ecr["pos"].isin(POSITIONS)].sort_values("ecr")
ecr["fp_overall_rank"] = np.arange(1, len(ecr) + 1)
ecr["fp_pos_rank"] = ecr.groupby("pos")["ecr"].rank(method="first").astype(int)
fpid = ids.dropna(subset=["fantasypros_id"]).copy()
fpid["fantasypros_id"] = fpid["fantasypros_id"].astype("int64").astype(str)
ecr = ecr.astype({"id": str}).merge(fpid.drop_duplicates("fantasypros_id")[["fantasypros_id", "gsis_id"]],
                                    left_on="id", right_on="fantasypros_id", how="inner")
fp = ecr.drop_duplicates("gsis_id")[["gsis_id", "fp_overall_rank", "fp_pos_rank"]]

# --- Model: first saved 2026 predictions
archived = sorted((PRED / "archive").glob("2026_jump_predictions_*.csv"))
preds = pd.read_csv(archived[0] if archived else PRED / "2026_jump_predictions.csv")
source = archived[0].stem.split("_")[-1] if archived else "current"
board = (m.merge(fp, on="gsis_id", how="left")
          .merge(preds[["player_id", "pred_ppg_2026", "baseline_ppg", "leap_prob_2026"]],
                 left_on="gsis_id", right_on="player_id", how="left"))
board = board.rename(columns={"espn_rank": "overall_rank", "espn_pos_rank": "expert_pos_rank"})
board["position"] = board["pos"]

# Model vs. ESPN inside each tested group (same rules as market_test.py)
parts = []
for pos, n in GROUP.items():
    g = board[(board["position"] == pos) & (board["expert_pos_rank"] <= n) & board["pred_ppg_2026"].notna()].copy()
    g["market_rank"] = g["expert_pos_rank"].rank(method="first")
    g["model_rank"] = g["pred_ppg_2026"].rank(ascending=False, method="first")
    g["tier"] = pd.cut(g["market_rank"].rank(pct=True), [0, 1 / 3, 2 / 3, 1], labels=TIERS).astype(str)
    g["verdict"], g["disagreement"] = verdicts(g)
    # Where the model would draft him, in ESPN's numbering (rookies and unrated players keep their slots)
    slots = np.sort(g["expert_pos_rank"].to_numpy())
    g["model_pos_rank"] = slots[g["model_rank"].astype(int).to_numpy() - 1]
    parts.append(g[["overall_rank", "market_rank", "model_rank", "model_pos_rank", "tier", "verdict", "disagreement"]])
board = board.merge(pd.concat(parts), on="overall_rank", how="left")
rookies = set(pd.read_parquet(RAW / "draft_picks.parquet", columns=["season", "gsis_id"])
              .query("season == 2026")["gsis_id"].dropna())
board["note"] = np.select(
    [board["position"] == "QB", board["gsis_id"].isin(rookies),
     board["pred_ppg_2026"].isna(), board["verdict"].isna()],
    ["QBs aren't modeled", "Rookie: no NFL track record yet",
     "Not modeled: fewer than 6 games (or too little usage) in 2025", "Outside the tested group"], "")

# --- Track record of each verdict, from the backtest (run against FantasyPros rankings)
bt = pd.read_csv(PRED / "market_backtest.csv").rename(columns={"market_tier": "tier"})
bt["verdict"], _ = verdicts(bt)
rec = (bt.groupby(["position", "tier", "verdict"])
       .agg(hist_players=("name", "size"), hist_beat_rate=("beat_market", lambda x: (x > 0).mean()))
       .reset_index())
rec_all = (bt.groupby(["tier", "verdict"])
           .agg(hist_players_all=("name", "size"), hist_beat_rate_all=("beat_market", lambda x: (x > 0).mean()))
           .reset_index())
board = board.merge(rec, on=["position", "tier", "verdict"], how="left").merge(rec_all, on=["tier", "verdict"], how="left")
rec_all.round(3).to_csv(PRED / "draft_board_verdict_record.csv", index=False)

out = board[["overall_rank", "player", "position", "team", "expert_pos_rank", "fp_overall_rank", "fp_pos_rank",
             "player_id", "pred_ppg_2026", "baseline_ppg", "leap_prob_2026", "market_rank", "model_rank",
             "model_pos_rank", "disagreement", "tier", "verdict", "hist_beat_rate", "hist_players",
             "hist_beat_rate_all", "hist_players_all", "note"]].copy()
out["rankings_source"] = "ESPN PPR Top 300"
out["rankings_date"], out["predictions_saved"] = "2026-09-08", source
out.sort_values("overall_rank").round(3).to_csv(PRED / "2026_draft_board.csv", index=False)

print(f"Draft board: {len(out)} players (ESPN rankings from 2026-09-08, model predictions saved {source})")
print(out["verdict"].value_counts(dropna=False).to_string(), flush=True)
