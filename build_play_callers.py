"""
build_play_callers.py
Turns the play-caller research into reference/play_callers.csv: one row per team-season with the
offensive play-caller at the START of the season (what's known before games are played).

Inputs (all in reference/):
  play_callers_draft.csv          every source's answer, side by side, with agreement checks
  play_caller_resolutions.csv     disagreements settled with team/local reporting, with links
  play_caller_sources/*.txt       the raw list from each article, with its URL

Run it:  python build_play_callers.py
"""
import re
from pathlib import Path

import pandas as pd

REF = Path("reference")
d = pd.read_csv(REF / "play_callers_draft.csv")
r = pd.read_csv(REF / "play_caller_resolutions.csv")
d = d.merge(r, on=["season", "team"], how="left")

# "Frank Reich / Thomas Brown" -> "Frank Reich": the preseason caller is listed first
d["play_caller"] = d["preseason_play_caller"].fillna(d["play_caller"].map(lambda s: re.split(r"\s*/\s*", str(s))[0].strip()))
d["midseason_change"] = d["midseason_change"].fillna("")
d["confidence"] = d.apply(
    lambda x: "resolved" if isinstance(x["resolution_sources"], str)
    else ("2+ sources agree" if x["n_sources"] >= 2 and x["all_agree"] else "1 source"), axis=1)
d["caller_role"] = d["role"].str.extract(r"^(HC|OC|co-OC|other)")[0].fillna("")
out = d[["season", "team", "play_caller", "caller_role", "midseason_change", "confidence", "n_sources",
         "sources", "resolution_sources"]].sort_values(["season", "team"])
out.to_csv(REF / "play_callers.csv", index=False)
print(out.groupby("season")["confidence"].value_counts().unstack(fill_value=0))
