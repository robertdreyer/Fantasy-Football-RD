"""
market_test.py
Does the model find players who beat their preseason ranking?

For each season 2020-2025 and each position, take the players the experts ranked before the season
(FantasyPros consensus, top 60 WR / 40 RB / 20 TE), rank them by the model's backtested prediction
(trained only on earlier seasons), and compare:
    market rank  = expert consensus rank within that group
    model rank   = rank of the model's predicted PPG within that group
    actual rank  = rank of the PPR points he actually scored (0 if he didn't play)
"Disagreement" = market rank - model rank (+ = the model likes him more than the experts do).
"Beat market"  = market rank - actual rank   (+ = he finished better than drafted).

Fair comparison: players are compared only with others the experts ranked similarly (early / middle /
late picks), and a regression checks whether the model's rank adds anything beyond the market's rank.

Outputs
  predictions/market_backtest.csv          one row per player-season tested
  predictions/market_backtest_summary.csv  early/middle/late picks: model likes more vs. less

Run it:  python market_test.py
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import jump_model as jm

warnings.filterwarnings("ignore")
TOP = {"WR": 60, "RB": 40, "TE": 20}        # roughly the drafted players at each position
OUT = Path("predictions")


def backtest_predictions(df, pos, cfg):
    """Model predictions for seasons 2019-2024 (-> 2020-2025 outcomes), each trained on earlier seasons only."""
    F = cfg["features"]
    d = jm.prepare(df, pos)
    pool = d[cfg["eligible"](d)].copy()
    lab = pool[(pool["season"] <= jm.LAST_LABELED_SEASON) & (pool["next_games"] >= 6)].copy()
    lab["c"] = lab["next_ppr_per_game"] - lab["baseline_ppg"]
    out = []
    for s in range(jm.FIRST_TEST_SEASON, jm.LAST_LABELED_SEASON + 1):
        tr = lab[lab["season"] < s]
        te = pool[pool["season"] == s].copy()          # everyone, including players who then got hurt
        te["pred_ppg"] = te["baseline_ppg"] + jm.change_model().fit(tr[F], tr["c"]).predict(te[F])
        out.append(te)
    return pd.concat(out)


def main():
    df = pd.read_parquet(jm.DATA)
    rows = []
    for pos, cfg in jm.POSITIONS.items():
        p = backtest_predictions(df, pos, cfg)
        p = p[p["next_preseason_rank"] <= TOP[pos]].copy()
        p["next_ppr"] = p["next_ppr"].fillna(0)        # missed the season = 0 points
        g = p.groupby("season")
        p["market_rank"] = g["next_preseason_rank"].rank(method="first")
        p["model_rank"] = g["pred_ppg"].rank(ascending=False, method="first")
        p["actual_rank"] = g["next_ppr"].rank(ascending=False, method="first")
        p["disagreement"] = p["market_rank"] - p["model_rank"]
        p["beat_market"] = p["market_rank"] - p["actual_rank"]
        p["position"] = pos
        rows.append(p)
    p = pd.concat(rows)
    p["outcome_season"] = p["season"] + 1
    p["grp"] = p["position"] + p["outcome_season"].astype(str)
    # Compare players the experts ranked about the same: split each position-season into thirds by
    # market rank, then within each third into "model likes more" vs "model likes less" halves.
    # (Comparing disagreement with "beat market" directly is misleading: both contain the market rank,
    # so even a random model would look good. A placebo with random ranks confirmed this.)
    g = p.groupby("grp")
    p["market_tier"] = pd.cut(g["market_rank"].rank(pct=True), [0, 1 / 3, 2 / 3, 1],
                              labels=["early picks", "middle picks", "late picks"])
    p["model_view"] = np.where(p.groupby(["grp", "market_tier"], observed=True)["disagreement"].rank(pct=True) > 0.5,
                               "model likes more", "model likes less")
    keep = ["outcome_season", "position", "name", "next_preseason_team", "market_tier", "market_rank", "model_rank",
            "actual_rank", "disagreement", "beat_market", "model_view", "pred_ppg", "next_ppr", "next_games"]
    OUT.mkdir(exist_ok=True)
    p[keep].round(2).to_csv(OUT / "market_backtest.csv", index=False)

    def table(x):
        return (x.groupby(["market_tier", "model_view"], observed=True)
                .agg(players=("name", "size"), avg_market_rank=("market_rank", "mean"),
                     avg_actual_rank=("actual_rank", "mean"),
                     share_beat_market=("beat_market", lambda v: (v > 0).mean()))
                .reset_index())
    summ = pd.concat([table(p).assign(position="ALL")] +
                     [table(x).assign(position=pos) for pos, x in p.groupby("position")]).round(3)
    summ.to_csv(OUT / "market_backtest_summary.csv", index=False)
    pd.set_option("display.width", 200)
    print(summ[summ["position"] == "ALL"].drop(columns="position").to_string(index=False))

    # Does the model's rank add information beyond the market's? (regression, clustered by position-season)
    import statsmodels.formula.api as smf
    base = smf.ols("actual_rank ~ market_rank * C(position)", p).fit()
    full = smf.ols("actual_rank ~ market_rank * C(position) + model_rank", p).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(p["grp"])[0]})
    print(f"\nModel rank, after accounting for market rank: coefficient {full.params['model_rank']:+.3f} "
          f"(p = {full.pvalues['model_rank']:.3f}); R-squared {base.rsquared:.3f} -> {full.rsquared:.3f}")

    def partial(x):     # model vs. actual, with the market rank's part removed from both
        res = lambda y: y - np.poly1d(np.polyfit(x["market_rank"], y, 1))(x["market_rank"])
        return spearmanr(res(x["model_rank"]), res(x["actual_rank"])).correlation
    pc = p.groupby(["position", "outcome_season"]).apply(partial).rename("partial_corr")
    print(f"Partial correlation, model vs. actual given market: average {pc.mean():+.3f}, "
          f"positive in {(pc > 0).sum()} of {len(pc)} position-seasons")
    print(pc.unstack(0).round(2).to_string())


if __name__ == "__main__":
    main()
