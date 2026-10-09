"""
draft_board.py
The 2026 draft board: every player in the experts' preseason PPR rankings (FantasyPros overall
consensus, last update before the Sept. 9 kickoff), with the model's view of each WR, RB and TE.

For each position, the model re-ranks the same players the experts ranked (top 60 WR / 40 RB / 20 TE,
the groups tested in market_test.py) by predicted 2026 PPG. Verdict:
    Value  = the model ranks him at least 10% of the group higher than the experts (6 WR / 4 RB / 2 TE spots)
    Reach  = the model ranks him at least that much lower
    Fair   = in between
Each verdict carries its track record from the 2020-2025 backtest (market_test.py): how often players
with the same verdict, in the same part of the draft (early / middle / late picks), beat their expert rank.

QBs, rookies and players outside the tested groups are listed with the experts' rank only.

Uses the FIRST saved 2026 predictions (predictions/archive), so the board can't change after the fact.

Output: predictions/2026_draft_board.csv  (committed; the website reads it)
Run it: python market_test.py   then   python draft_board.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw")
PRED = Path("predictions")
KICKOFF_2026 = "2026-09-09"
GROUP = {"WR": 60, "RB": 40, "TE": 20}
POSITIONS = ["WR", "RB", "TE", "QB"]          # kickers and defenses left off
TIERS = ["early picks", "middle picks", "late picks"]


def verdicts(df, rank_col="market_rank", model_col="model_rank", pos_col="position"):
    k = df[pos_col].map(GROUP) * 0.10
    dis = df[rank_col] - df[model_col]
    return np.select([dis >= k, dis <= -k], ["Value", "Reach"], "Fair"), dis


# --- Experts: overall PPR consensus, last scrape before kickoff
ecr = pd.read_parquet(RAW / "ecr_rankings.parquet")
ecr = ecr[ecr["fp_page"].str.contains(r"(?:^|/)ppr-cheatsheets") & ecr["scrape_date"].between("2026-01-01", KICKOFF_2026)
          & (ecr["scrape_date"] < KICKOFF_2026)]
ecr = ecr[ecr["scrape_date"] == ecr["scrape_date"].max()].copy()
scraped = ecr["scrape_date"].iloc[0][:10]
ecr["pos"] = ecr["pos"].str.extract(r"^([A-Z]+)")[0]
ecr = ecr[ecr["pos"].isin(POSITIONS)].sort_values("ecr")
ecr["overall_rank"] = np.arange(1, len(ecr) + 1)
ecr["expert_pos_rank"] = ecr.groupby("pos")["ecr"].rank(method="first").astype(int)
ids = pd.read_parquet(RAW / "ff_playerids.parquet", columns=["fantasypros_id", "gsis_id"]).dropna()
ids["fantasypros_id"] = ids["fantasypros_id"].astype("int64").astype(str)      # 28013.0 -> "28013"
ids = ids.drop_duplicates("fantasypros_id")
ecr = ecr.astype({"id": str}).merge(ids, left_on="id", right_on="fantasypros_id", how="left")

# --- Model: first saved 2026 predictions
archived = sorted((PRED / "archive").glob("2026_jump_predictions_*.csv"))
preds = pd.read_csv(archived[0] if archived else PRED / "2026_jump_predictions.csv")
source = archived[0].stem.split("_")[-1] if archived else "current"
board = ecr.merge(preds[["player_id", "pred_ppg_2026", "baseline_ppg", "leap_prob_2026", "next_qb_name"]
                        if "next_qb_name" in preds else ["player_id", "pred_ppg_2026", "baseline_ppg", "leap_prob_2026"]],
                  left_on="gsis_id", right_on="player_id", how="left")
board["position"] = board["pos"]

# Model vs. experts inside each tested group (same rules as market_test.py)
parts = []
for pos, n in GROUP.items():
    g = board[(board["position"] == pos) & (board["expert_pos_rank"] <= n) & board["pred_ppg_2026"].notna()].copy()
    g["market_rank"] = g["expert_pos_rank"].rank(method="first")
    g["model_rank"] = g["pred_ppg_2026"].rank(ascending=False, method="first")
    g["tier"] = pd.cut(g["market_rank"].rank(pct=True), [0, 1 / 3, 2 / 3, 1], labels=TIERS).astype(str)
    g["verdict"], g["disagreement"] = verdicts(g)
    # Where the model would draft him, in the experts' numbering (rookies and unrated players keep their slots)
    slots = np.sort(g["expert_pos_rank"].to_numpy())
    g["model_pos_rank"] = slots[g["model_rank"].astype(int).to_numpy() - 1]
    parts.append(g[["id", "market_rank", "model_rank", "model_pos_rank", "tier", "verdict", "disagreement"]])
board = board.merge(pd.concat(parts), on="id", how="left")
rookies = set(pd.read_parquet(RAW / "draft_picks.parquet", columns=["season", "gsis_id"])
              .query("season == 2026")["gsis_id"].dropna())
board["note"] = np.select(
    [board["position"] == "QB", board["gsis_id"].isin(rookies),
     board["pred_ppg_2026"].isna(), board["verdict"].isna()],
    ["QBs aren't modeled", "Rookie: no NFL track record yet",
     "Not modeled: fewer than 6 games (or too little usage) in 2025", "Outside the tested group"], "")

# --- Track record of each verdict, from the backtest
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

out = board[["overall_rank", "ecr", "player", "position", "team", "expert_pos_rank", "player_id", "pred_ppg_2026",
             "baseline_ppg", "leap_prob_2026", "market_rank", "model_rank", "model_pos_rank", "disagreement", "tier", "verdict",
             "hist_beat_rate", "hist_players", "hist_beat_rate_all", "hist_players_all", "note"]].copy()
out["team"] = out["team"].replace({"JAC": "JAX", "LAR": "LA"})
out["rankings_date"], out["predictions_saved"] = scraped, source
out.round(3).to_csv(PRED / "2026_draft_board.csv", index=False)

print(f"Draft board: {len(out)} players (experts' rankings from {scraped}, model predictions saved {source})")
print(out["verdict"].value_counts(dropna=False).to_string(), flush=True)
print("\nBacktest record by verdict (all positions):")
print(rec_all.round(2).to_string(index=False))
