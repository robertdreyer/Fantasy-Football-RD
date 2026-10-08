"""
jump_model.py
Step 3: predict which players will beat their own track record next season.

For each position (WR, TE, RB) it fits two models:
  - change model : next season's PPR points per game minus his baseline (ridge regression)
  - leap model   : probability of a big leap (logistic regression)
Baseline = games-weighted PPR points per game over the current and previous season.

It backtests each model season by season (train on earlier seasons only), then
retrains on everything through 2024 and scores the 2025 seasons -> 2026 predictions.

Outputs (committed to GitHub, so the predictions are on record before results come in):
  predictions/2026_jump_predictions.csv   one row per player with predicted 2026 PPG
  predictions/backtest_summary.csv        how each model did on past seasons

If reference/coordinators.csv exists (collect_coordinators.py), coordinator features
are added automatically.

Run it:  python jump_model.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DATA = Path("data/processed/player_seasons.parquet")
OUT = Path("predictions")
FIRST_TEST_SEASON, LAST_LABELED_SEASON, PREDICT_FROM = 2019, 2024, 2025

# Shared building blocks -----------------------------------------------------
TRACK_RECORD = ["baseline_ppg", "ppr_per_game", "second_half_trend"]
CAREER = ["age", "years_exp", "draft_pick_filled"]
NEXT_SEASON = ["next_preseason_depth_tier", "depth_promotion", "changed_team"]
ENVIRONMENT = ["qb_epa_per_dropback", "team_pass_rate_over_exp", "games_missed"]
COACHING = ["oc_changed", "next_oc_prior_pass_rate_over_exp"]     # used only if coordinators exist

# What counts as a fantasy-relevant "big leap", and who is eligible, per position.
POSITIONS = {
    "WR": dict(
        features=TRACK_RECORD + CAREER + NEXT_SEASON + ENVIRONMENT + [
            "tprr", "yprr", "fp_over_expected_per_game", "adot", "target_share", "route_participation",
            "xfp_per_game", "rz_target_share", "next_team_vacated_target_share", "next_sos_pass_def_epa"],
        eligible=lambda d: (d["games"] >= 6) & (d["routes"] >= 100),
        leap_gain=4, leap_floor=14),
    "TE": dict(
        features=TRACK_RECORD + CAREER + NEXT_SEASON + ENVIRONMENT + [
            "tprr", "yprr", "fp_over_expected_per_game", "target_share", "route_participation",
            "xfp_per_game", "rz_target_share", "next_team_vacated_target_share", "next_sos_pass_def_epa"],
        eligible=lambda d: (d["games"] >= 6) & (d["routes"] >= 100),
        leap_gain=3, leap_floor=11),          # TEs score less, so a smaller leap counts
    "RB": dict(
        features=TRACK_RECORD + CAREER + NEXT_SEASON + ENVIRONMENT + [
            "carries_per_game", "targets_per_game", "target_share", "xfp_per_game",
            "fp_over_expected_per_game", "explosive_run_rate", "yac_per_carry", "ryoe_per_carry",
            "rz_carry_share", "gl_carry_share", "tprr",
            "next_team_vacated_carry_share", "next_team_vacated_target_share",
            "team_epa_per_rush", "team_run_stuff_rate", "team_8plus_box_rate", "next_sos_rush_def_epa"],
        eligible=lambda d: (d["games"] >= 6) & ((d["carries"] + d["targets"]) >= 50),
        leap_gain=4, leap_floor=14),
}


def change_model():
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), Ridge(alpha=10))


def leap_model():
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(C=0.5, max_iter=2000))


def prepare(df, pos):
    """Add baseline and helper columns for one position."""
    d = df[df["position"] == pos].copy()
    prev = (d[["player_id", "season", "ppr", "games"]].assign(season=lambda x: x["season"] + 1)
            .rename(columns={"ppr": "prev_ppr", "games": "prev_games"}))
    d = d.merge(prev, on=["player_id", "season"], how="left")
    d["baseline_ppg"] = (d["ppr"] + d["prev_ppr"].fillna(0)) / (d["games"] + d["prev_games"].fillna(0))
    d["draft_pick_filled"] = d["draft_pick"].fillna(300)
    d["depth_promotion"] = d["preseason_depth_tier"] - d["next_preseason_depth_tier"]
    return d


def run_position(df, pos, cfg, has_coaches):
    features = cfg["features"] + (COACHING if has_coaches else [])
    d = prepare(df, pos)
    pool = d[cfg["eligible"](d)].copy()

    lab = pool[(pool["season"] <= LAST_LABELED_SEASON) & (pool["next_games"] >= 6)].copy()
    lab["ppg_change"] = lab["next_ppr_per_game"] - lab["baseline_ppg"]
    lab["leap"] = ((lab["ppg_change"] >= cfg["leap_gain"]) &
                   (lab["next_ppr_per_game"] >= cfg["leap_floor"])).astype(int)

    # Backtest: each season predicted by a model trained only on earlier seasons
    bt = []
    for season in range(FIRST_TEST_SEASON, LAST_LABELED_SEASON + 1):
        tr, te = lab[lab["season"] < season], lab[lab["season"] == season]
        o = te[["player_id", "name", "season", "ppg_change", "leap"]].copy()
        o["pred_change"] = change_model().fit(tr[features], tr["ppg_change"]).predict(te[features])
        o["leap_prob"] = leap_model().fit(tr[features], tr["leap"]).predict_proba(te[features])[:, 1]
        bt.append(o)
    bt = pd.concat(bt)
    top = bt.groupby("season")["pred_change"].transform(lambda s: s >= s.quantile(0.9))
    bottom = bt.groupby("season")["pred_change"].transform(lambda s: s <= s.quantile(0.1))
    summary = {
        "position": pos, "seasons_tested": f"{FIRST_TEST_SEASON}-{LAST_LABELED_SEASON}",
        "players_tested": len(bt), "leap_rate": bt["leap"].mean(),
        "naive_avg_miss_ppg": bt["ppg_change"].abs().mean(),
        "model_avg_miss_ppg": (bt["ppg_change"] - bt["pred_change"]).abs().mean(),
        "corr_pred_vs_actual": np.corrcoef(bt["pred_change"], bt["ppg_change"])[0, 1],
        "top10pct_actual_change": bt.loc[top, "ppg_change"].mean(),
        "bottom10pct_actual_change": bt.loc[bottom, "ppg_change"].mean(),
        "leap_auc": roc_auc_score(bt["leap"], bt["leap_prob"]),
        "coaching_features": has_coaches,
    }

    # Final models: all labeled seasons -> score 2025 players for 2026
    cm = change_model().fit(lab[features], lab["ppg_change"])
    lm = leap_model().fit(lab[features], lab["leap"])
    weights = pd.Series(cm[-1].coef_[:len(features)], index=features, name=pos)

    now = pool[pool["season"] == PREDICT_FROM].copy()
    now["pred_change_2026"] = cm.predict(now[features])
    now["pred_ppg_2026"] = now["baseline_ppg"] + now["pred_change_2026"]
    now["leap_prob_2026"] = lm.predict_proba(now[features])[:, 1]
    keep = ["player_id", "name", "position", "team", "next_preseason_team", "age", "ppr_per_game",
            "baseline_ppg", "pred_change_2026", "pred_ppg_2026", "leap_prob_2026", "next_preseason_rank"]
    return now[keep], summary, weights


def main():
    OUT.mkdir(exist_ok=True)
    df = pd.read_parquet(DATA)
    has_coaches = "oc_changed" in df.columns and df["oc_changed"].notna().any()
    if not has_coaches:
        print("No coordinator data yet: models run without coaching features.")

    preds, summaries, weights = [], [], []
    for pos, cfg in POSITIONS.items():
        p, s, w = run_position(df, pos, cfg, has_coaches)
        preds.append(p); summaries.append(s); weights.append(w)
        print(f"{pos}: {s['players_tested']} seasons tested | avg miss {s['naive_avg_miss_ppg']:.2f} naive -> "
              f"{s['model_avg_miss_ppg']:.2f} model | corr {s['corr_pred_vs_actual']:.2f} | "
              f"top 10% {s['top10pct_actual_change']:+.2f}, bottom 10% {s['bottom10pct_actual_change']:+.2f} | "
              f"leap AUC {s['leap_auc']:.2f}")

    preds = pd.concat(preds).sort_values("pred_ppg_2026", ascending=False)
    preds["position_rank_pred"] = preds.groupby("position")["pred_ppg_2026"].rank(ascending=False, method="first").astype(int)
    preds.round(3).to_csv(OUT / "2026_jump_predictions.csv", index=False)
    pd.DataFrame(summaries).round(3).to_csv(OUT / "backtest_summary.csv", index=False)
    pd.concat(weights, axis=1).round(3).to_csv(OUT / "model_weights.csv")
    print(f"\nSaved {len(preds)} 2026 predictions -> {OUT / '2026_jump_predictions.csv'}")


if __name__ == "__main__":
    main()
