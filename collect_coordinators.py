"""
collect_coordinators.py
Builds reference/coordinators_wikipedia.csv: head coach, offensive coordinator (OC) and
defensive coordinator (DC) for every team, 2016-2026, from each team-season's Wikipedia page.

Wikipedia is only the FIRST source. Every coordinator change and mid-season change is then
checked against other sites, and the verified table is saved as reference/coordinators.csv
(see reference/coordinators_verification.csv for what was checked and where).

Uses the official Wikipedia API, about one request per second (~6 minutes for 352 pages).
Saves after every page, so if it stops you can run it again and it resumes.

Run it:  python collect_coordinators.py
"""

import csv
import html
import re
import time
from pathlib import Path

import requests

SEASONS = range(2016, 2027)
WAIT_SECONDS = 1
OUT = Path("reference/coordinators_wikipedia.csv")
API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "FantasyFootballRD/1.0 (personal research project; robertdreyer12@gmail.com)"}

# nflverse code -> Wikipedia team name, by season (relocations and renames)
def team_name(code, season):
    special = {
        "LAC": "San Diego Chargers" if season == 2016 else "Los Angeles Chargers",
        "LV": "Oakland Raiders" if season <= 2019 else "Las Vegas Raiders",
        "WAS": ("Washington Redskins" if season <= 2019 else
                "Washington Football Team" if season <= 2021 else "Washington Commanders"),
    }
    names = {
        "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
        "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
        "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
        "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
        "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
        "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "MIA": "Miami Dolphins",
        "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints",
        "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
        "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers",
        "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans",
    }
    return special.get(code) or names[code]


TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
         "HOU", "IND", "JAX", "KC", "LV", "LAC", "LA", "MIA", "MIN", "NE", "NO", "NYG",
         "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"]
FIELDS = ["season", "team", "head_coach", "oc", "dc", "page"]
LABELS = {"head_coach": "Head coach", "oc": "Offensive coordinator", "dc": "Defensive coordinator"}


def infobox_value(page_html, label):
    """Text of the infobox row whose label is `label`. Several people (mid-season change)
    are joined with ' / ' in the order Wikipedia lists them."""
    m = re.search(r"<th[^>]*>\s*(?:<[^>]+>)*\s*" + re.escape(label) + r"\s*(?:<[^>]+>)*\s*</th>\s*<td[^>]*>(.*?)</td>",
                  page_html, re.S | re.I)
    if not m:
        return ""
    cell = re.sub(r"<br\s*/?>|</li>|</p>", "\n", m.group(1))
    cell = re.sub(r"<sup.*?</sup>", "", cell, flags=re.S)        # footnote markers
    cell = html.unescape(re.sub(r"<[^>]+>", "", cell))
    people = []
    for line in cell.split("\n"):
        line = re.sub(r"\[\d+\]|\([^)]*\)", "", line).strip(" ,; ")   # drop [1] and "(interim)"
        if line:
            people.append(line)
    return " / ".join(people)


def main():
    OUT.parent.mkdir(exist_ok=True)
    done = set()
    if OUT.exists():
        with OUT.open(newline="", encoding="utf-8") as f:
            done = {(int(r["season"]), r["team"]) for r in csv.DictReader(f)}
    todo = [(s, t) for s in SEASONS for t in TEAMS if (s, t) not in done]
    print(f"{len(done)} already saved, {len(todo)} to fetch (~{len(todo) * (WAIT_SECONDS + 0.5) / 60:.0f} min)")

    new_file = not OUT.exists()
    with OUT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for i, (season, team) in enumerate(todo, 1):
            title = f"{season} {team_name(team, season)} season"
            params = {"action": "parse", "page": title, "prop": "text", "section": 0,
                      "format": "json", "formatversion": 2, "redirects": 1}
            resp = requests.get(API, params=params, headers=HEADERS, timeout=30)
            data = resp.json() if resp.ok else {}
            if "parse" not in data:
                print(f"  {title}: page not found ({data.get('error', {}).get('info', resp.status_code)}), skipped")
                time.sleep(WAIT_SECONDS)
                continue
            page_html = data["parse"]["text"]
            row = {"season": season, "team": team, "page": title}
            for key, label in LABELS.items():
                row[key] = infobox_value(page_html, label)
            if i == 1 and not (row["oc"] or row["head_coach"]):
                print("Couldn't read the infobox on the first page; the page layout may differ from expected.\n"
                      "Paste this output so the parser can be fixed:\n", page_html[:1500])
                return
            writer.writerow(row)
            f.flush()
            print(f"  [{i}/{len(todo)}] {season} {team}: HC {row['head_coach'] or '?'} | "
                  f"OC {row['oc'] or '?'} | DC {row['dc'] or '?'}")
            time.sleep(WAIT_SECONDS)

    print(f"\nDone -> {OUT}\nNext: tell Claude it's ready, so the changes can be cross-checked "
          "against other sources before the data is used.")


if __name__ == "__main__":
    main()
