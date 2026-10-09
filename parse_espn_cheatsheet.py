"""
parse_espn_cheatsheet.py
Turns ESPN's PPR Top 300 cheat sheet (PDF from the ESPN Fantasy draft kit) into
reference/espn_2026_ppr_top300.csv: espn_rank, pos, espn_pos_rank, player, team, auction, bye.

Needs pdftotext (poppler). On Windows with Anaconda:  conda install -c conda-forge poppler
Run it:  python parse_espn_cheatsheet.py path\\to\\NFL26_CS_PPR300.pdf
"""
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

pdf = Path(sys.argv[1])
text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
pat = re.compile(r"(\d+)\.\s+\(([A-Z/]+?)(\d+)\)\s+(.+?),\s+([A-Z]{2,3})\s+\$(\d+)\s+(\d+)")
rows = [dict(espn_rank=int(a), pos=b, espn_pos_rank=int(c), player=d.strip(), team=e, auction=int(f), bye=int(g))
        for a, b, c, d, e, f, g in pat.findall(text)]
df = pd.DataFrame(rows).drop_duplicates("espn_rank").sort_values("espn_rank")   # the legend repeats rank 1
assert df["espn_rank"].tolist() == list(range(1, len(df) + 1)), "ranks are not a complete 1..N list"
out = Path("reference/espn_2026_ppr_top300.csv")
df.to_csv(out, index=False)
print(f"{len(df)} players -> {out}")
