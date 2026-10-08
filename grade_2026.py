"""
grade_2026.py
Grades the 2026 predictions against what has actually happened so far.

This is the ONLY script that touches 2026 game results, and it keeps them in a
separate folder (data/actuals/), so they can never leak into the models.

Run any time during the season (results are noisy until ~8 games):
    python grade_2026.py

Outputs:
  data/actuals/player_stats_2026.parquet   raw 2026 weekly stats (not committed)
  predictions/2026_grades.csv              each player's prediction vs. actual so far
  predictions/2026_grade_summary.csv       one line per position per run (history kept)
"""

from datetime import date
from pathlib import Path

import nflreadpy as nfl
import numpy as np
import pandas as pd

PRED = Path("predictions/2026_jump_predictions.csv")
ACTUALS = Path("data/actuals")
ACTUALS.mkdir(parents=True, exist_ok=True)
MIN_GAMES = 2

stats = nfl.load_player_stats(2026).to_pandas()
stats.to_parquet(ACTUALS / "player_stats_2026.parquet", index=False)
stats = stats[stats["season_type"] == "REG"]
through_week = int(stats["week"].max())

actual = (stats.groupby("player_id")
          .agg(games_2026=("game_id", "nunique"), ppr_2026=("fantasy_points_ppr", "sum"),
               team_2026=("team", "last"))
          .reset_index())
actual["ppg_2026"] = actual["ppr_2026"] / actual["games_2026"]

preds = pd.read_csv(PRED)
g = preds.merge(actual, on="player_id", how="left")
g["actual_change"] = g["ppg_2026"] - g["baseline_ppg"]
g["model_miss"] = (g["ppg_2026"] - g["pred_ppg_2026"]).abs()
g["naive_miss"] = (g["ppg_2026"] - g["baseline_ppg"]).abs()     # "he'll repeat his baseline"
g["through_week"] = through_week
g.round(3).to_csv("predictions/2026_grades.csv", index=False)

played = g[g["games_2026"] >= MIN_GAMES]
rows = []
for pos, x in played.groupby("position"):
    top = x["pred_change_2026"] >= x["pred_change_2026"].quantile(0.8)
    rows.append({
        "run_date": date.today().isoformat(), "through_week": through_week, "position": pos,
        "players": len(x),
        "naive_avg_miss_ppg": x["naive_miss"].mean(),
        "model_avg_miss_ppg": x["model_miss"].mean(),
        "corr_pred_vs_actual_change": np.corrcoef(x["pred_change_2026"], x["actual_change"])[0, 1],
        "top20pct_pred_actual_change": x.loc[top, "actual_change"].mean(),
        "others_actual_change": x.loc[~top, "actual_change"].mean(),
    })
summary = pd.DataFrame(rows).round(3)

hist_path = Path("predictions/2026_grade_summary.csv")
if hist_path.exists():
    old = pd.read_csv(hist_path)
    summary = pd.concat([old[old["through_week"] != through_week], summary], ignore_index=True)
summary.to_csv(hist_path, index=False)

print(f"2026 results through week {through_week} (players with {MIN_GAMES}+ games)\n")
print(summary[summary["through_week"] == through_week].to_string(index=False))
print("\nTop-10 leap candidates per position, so far:")
cols = ["name", "position", "baseline_ppg", "pred_ppg_2026", "leap_prob_2026", "games_2026", "ppg_2026"]
print(g.sort_values("leap_prob_2026", ascending=False).groupby("position").head(10)[cols]
      .sort_values(["position", "leap_prob_2026"], ascending=[True, False]).round(2).to_string(index=False))
