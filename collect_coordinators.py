"""
collect_coordinators.py
Builds reference/coordinators.csv: head coach, offensive coordinator (OC) and
defensive coordinator (DC) for every team, 2016-2026, from Pro Football Reference.

Why a separate script: nflverse doesn't have coordinators, and Pro Football Reference
limits automated requests (about 20 per minute). This script waits between pages,
so the first full run takes ~25 minutes. It saves after every page, so if it stops
you can just run it again and it picks up where it left off.

The output goes in reference/ (not data/) so it IS committed to GitHub. You can
open the CSV and fix anything by hand, e.g. a coordinator fired mid-season.

Run it:  python collect_coordinators.py
"""

import csv
import re
import time
from pathlib import Path

import requests

SEASONS = range(2016, 2027)   # 2026 = this season's preseason staff
WAIT_SECONDS = 4               # stay under PFR's rate limit
OUT = Path("reference/coordinators.csv")
OUT.parent.mkdir(exist_ok=True)

# nflverse team code -> Pro Football Reference franchise code (constant across relocations)
PFR_CODES = {
    "ARI": "crd", "ATL": "atl", "BAL": "rav", "BUF": "buf", "CAR": "car", "CHI": "chi",
    "CIN": "cin", "CLE": "cle", "DAL": "dal", "DEN": "den", "DET": "det", "GB": "gnb",
    "HOU": "htx", "IND": "clt", "JAX": "jax", "KC": "kan", "LV": "rai", "LAC": "sdg",
    "LA": "ram", "MIA": "mia", "MIN": "min", "NE": "nwe", "NO": "nor", "NYG": "nyg",
    "NYJ": "nyj", "PHI": "phi", "PIT": "pit", "SEA": "sea", "SF": "sfo", "TB": "tam",
    "TEN": "oti", "WAS": "was",
}
FIELDS = ["season", "team", "head_coach", "oc", "dc", "head_coach_id", "oc_id", "dc_id"]
LABELS = {"head_coach": "Coach", "oc": "Offensive Coordinator", "dc": "Defensive Coordinator"}


def parse_role(html, label):
    """Return (names, ids) listed after e.g. 'Offensive Coordinator:' on a PFR team page.
    If a team changed coordinators mid-season, PFR lists more than one; we keep them all,
    joined with ' / ', in the order PFR shows them."""
    m = re.search(r"(?<![A-Za-z ])" + re.escape(label) + r":", html)
    if label == "Coach":   # avoid matching the 'Coordinator' labels
        m = re.search(r">\s*Coach:", html)
    if not m:
        return "", ""
    end = html.find("</p>", m.end())
    chunk = html[m.end(): end if end != -1 else m.end() + 600]
    links = re.findall(r'href="(?:https://www\.pro-football-reference\.com)?/coaches/([^"/]+)\.htm"[^>]*>([^<]+)</a>', chunk)
    if links:
        return " / ".join(n.strip() for _, n in links), " / ".join(i for i, _ in links)
    text = re.sub(r"<[^>]+>", "", chunk)
    text = re.sub(r"\(\d+-\d+-\d+\)", "", text)          # drop W-L record after head coach
    return text.strip(" :\n\t"), ""


def main():
    done = set()
    if OUT.exists():
        with OUT.open(newline="", encoding="utf-8") as f:
            done = {(int(r["season"]), r["team"]) for r in csv.DictReader(f)}

    new_file = not OUT.exists()
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (personal fantasy football research project)"

    with OUT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        todo = [(s, t) for s in SEASONS for t in PFR_CODES if (s, t) not in done]
        print(f"{len(done)} already saved, {len(todo)} to fetch (~{len(todo) * WAIT_SECONDS // 60} min)")

        for i, (season, team) in enumerate(todo, 1):
            url = f"https://www.pro-football-reference.com/teams/{PFR_CODES[team]}/{season}.htm"
            resp = session.get(url, timeout=30)
            if resp.status_code == 429:
                print("Rate-limited by PFR. Wait an hour, then run the script again to resume.")
                return
            if resp.status_code != 200:
                print(f"  {season} {team}: HTTP {resp.status_code}, skipped")
                time.sleep(WAIT_SECONDS)
                continue

            row = {"season": season, "team": team}
            for key, label in LABELS.items():
                names, ids = parse_role(resp.text, label)
                row[key], row[f"{key}_id"] = names, ids
            if i == 1 and not row["oc"] and not row["dc"]:
                print("Couldn't find coordinators on the first page. PFR's layout may have changed.\n"
                      f"Open {url} to check, and share this message so the parser can be fixed.")
                return
            writer.writerow(row)
            f.flush()
            print(f"  [{i}/{len(todo)}] {season} {team}: OC {row['oc'] or '?'} | DC {row['dc'] or '?'}")
            time.sleep(WAIT_SECONDS)

    print(f"\nDone -> {OUT}")


if __name__ == "__main__":
    main()
