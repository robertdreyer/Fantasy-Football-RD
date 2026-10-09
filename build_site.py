"""
build_site.py
Builds the project website from the files in predictions/ -> site/index.html

One self-contained page (no server, no external libraries), published with GitHub Pages.
Re-run after jump_model.py or grade_2026.py and the site picks up the new numbers.

Run it:  python build_site.py      then open site/index.html in a browser
"""

import json
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PRED = Path("predictions")
SITE = Path("site")
SITE.mkdir(exist_ok=True)

# Links to the notebooks. In GitHub Actions, GITHUB_REPOSITORY is "username/repo".
REPO = os.environ.get("GITHUB_REPOSITORY", "")
REPO_URL = f"https://github.com/{REPO}" if REPO else ""

# ---------------------------------------------------------------------------
# Gather the data
# ---------------------------------------------------------------------------
preds = pd.read_csv(PRED / "2026_jump_predictions.csv")
grades_path = PRED / "2026_grades.csv"
if grades_path.exists():
    grades = pd.read_csv(grades_path)
    actual_cols = ["player_id", "games_2026", "ppg_2026", "through_week"]
    preds = preds.merge(grades[actual_cols], on="player_id", how="left")
else:
    preds["games_2026"], preds["ppg_2026"], preds["through_week"] = np.nan, np.nan, np.nan
through_week = int(preds["through_week"].max()) if preds["through_week"].notna().any() else None

push_cols = [c for c in preds.columns if c.startswith("push_")]
players = []
for r in preds.itertuples(index=False):
    d = r._asdict()
    players.append({
        "name": d["name"], "pos": d["position"],
        "team": d["next_preseason_team"] if isinstance(d["next_preseason_team"], str) else d["team"],
        "qb": d.get("next_qb_name") if isinstance(d.get("next_qb_name"), str) else "",
        "age": d["age"], "base": d["baseline_ppg"], "pred": d["pred_ppg_2026"],
        "chg": d["pred_change_2026"], "leap": d["leap_prob_2026"],
        "rank": d["next_preseason_rank"], "g26": d["games_2026"], "ppg26": d["ppg_2026"],
        "up": d.get("factors_up") if isinstance(d.get("factors_up"), str) else "",
        "down": d.get("factors_down") if isinstance(d.get("factors_down"), str) else "",
        "push": {c[5:]: d[c] for c in push_cols},
    })

backtest = pd.read_csv(PRED / "backtest_summary.csv").to_dict("records")
summary_path = PRED / "2026_grade_summary.csv"
live = pd.read_csv(summary_path).to_dict("records") if summary_path.exists() else []


def clean(x):
    """JSON can't hold NaN: turn it into null, and round floats to keep the page small."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else round(float(x), 3)
    if isinstance(x, np.integer):
        return int(x)
    return x


data = clean({"players": players, "backtest": backtest, "live": live,
              "throughWeek": through_week, "updated": date.today().strftime("%B %-d, %Y") if os.name != "nt"
              else date.today().strftime("%B %#d, %Y"), "repo": REPO_URL})

# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fantasy Football RD: 2026 Breakout Model</title>
<meta name="description" content="Which NFL players will beat their own track record in 2026? Backtested models for WR, TE and RB, graded live through the season.">
<style>
:root {
  --bg: #f7f6f3; --surface: #ffffff; --surface-2: #f0efec; --line: #e3e1dc;
  --ink: #141413; --ink-2: #55544f; --ink-3: #8a8983;
  --accent: #2a78d6; --accent-soft: #e3eefb; --up: #2a78d6; --down: #e34948; --pred: #eb6834;
  --radius: 12px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141413; --surface: #1d1d1b; --surface-2: #262624; --line: #33332f;
    --ink: #f4f3ee; --ink-2: #c3c2b7; --ink-3: #8f8e86;
    --accent: #5598e7; --accent-soft: #1d3150; --up: #5598e7; --down: #e66767; --pred: #f08a5d;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 0 16px; }
header { padding: 40px 0 8px; }
.eyebrow { color: var(--accent); font-weight: 600; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; }
h1 { font-size: clamp(26px, 4.4vw, 40px); line-height: 1.15; margin: 6px 0 10px; letter-spacing: -.01em; }
.lede { color: var(--ink-2); max-width: 720px; margin: 0 0 6px; font-size: 16px; }
.meta { color: var(--ink-3); font-size: 13px; }
.meta a, .method a, footer a { color: var(--accent); }
h2 { font-size: 20px; margin: 36px 0 4px; }
.sub { color: var(--ink-2); margin: 0 0 14px; font-size: 14px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; }
.card h3 { margin: 0 0 10px; font-size: 14px; color: var(--ink-2); font-weight: 600; }
.stat { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; padding: 4px 0; font-size: 14px; color: var(--ink-2); }
.stat b { white-space: nowrap; font-size: 18px; color: var(--ink); font-variant-numeric: tabular-nums; }
.pos-up { color: var(--up) !important; } .pos-down { color: var(--down) !important; }
.tabs { display: inline-flex; background: var(--surface-2); border-radius: 999px; padding: 4px; gap: 4px; margin: 6px 0 16px; }
.tabs button { border: 0; background: transparent; color: var(--ink-2); font: inherit; font-weight: 600;
  padding: 8px 18px; border-radius: 999px; cursor: pointer; }
.tabs button[aria-selected="true"] { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
.leaps { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
.leap { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px; }
.leap .top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.leap .nm { font-weight: 650; font-size: 16px; }
.leap .tm { color: var(--ink-3); font-size: 13px; }
.pct { font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
.leap .nums { display: flex; gap: 14px; margin: 8px 0; font-size: 13px; color: var(--ink-2); flex-wrap: wrap; }
.leap .nums b { color: var(--ink); font-variant-numeric: tabular-nums; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: 12px; padding: 3px 8px; border-radius: 999px; background: var(--surface-2); color: var(--ink-2); }
.chip.up::before { content: "▲ "; color: var(--up); } .chip.down::before { content: "▼ "; color: var(--down); }
.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 14px 0 10px; }
.toolbar input[type="search"] { flex: 1 1 220px; max-width: 320px; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); font: inherit; }
.toolbar label { color: var(--ink-2); font-size: 14px; display: flex; gap: 6px; align-items: center; }
.tablewrap { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 10px; text-align: right; white-space: nowrap; border-bottom: 1px solid var(--line); }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3) { text-align: left; }
th { font-size: 12px; color: var(--ink-2); font-weight: 600; cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--surface); }
th[aria-sort="descending"]::after { content: " ↓"; } th[aria-sort="ascending"]::after { content: " ↑"; }
tbody tr.row { cursor: pointer; } tbody tr.row:hover { background: var(--surface-2); }
tr.detail td { text-align: left; background: var(--surface-2); white-space: normal; }
.why { display: grid; grid-template-columns: minmax(150px, 220px) 1fr; gap: 4px 12px; align-items: center; max-width: 640px; }
.why .lbl { font-size: 13px; color: var(--ink-2); }
.bar { position: relative; height: 14px; }
.bar .mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--ink-3); }
.bar .fill { position: absolute; top: 2px; height: 10px; border-radius: 3px; }
.why-note { font-size: 12px; color: var(--ink-3); margin-top: 8px; }
.chart { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 12px; position: relative; }
.chart svg { width: 100%; height: auto; display: block; }
.chart text { fill: var(--ink-3); font-size: 11px; }
.tip { position: absolute; pointer-events: none; background: var(--ink); color: var(--bg); font-size: 12px;
  padding: 6px 8px; border-radius: 6px; opacity: 0; transition: opacity .1s; white-space: nowrap; }
.legend { display: flex; gap: 16px; font-size: 13px; color: var(--ink-2); margin: 8px 4px 0; flex-wrap: wrap; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.method { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 6px 20px; }
.method li { margin: 8px 0; color: var(--ink-2); } .method b { color: var(--ink); }
footer { color: var(--ink-3); font-size: 13px; padding: 36px 0 48px; }
.empty { padding: 20px; color: var(--ink-3); }
@media (max-width: 640px) { .hide-sm { display: none; } .why { grid-template-columns: 120px 1fr; } }
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">Fantasy Football RD</div>
  <h1>Who will beat their own track record in 2026?</h1>
  <p class="lede">Models trained on 2016–2025 NFL data predict how much each WR, TE and RB will improve on his
  recent scoring, and who is most likely to make a big leap. Predictions use only information available before the
  2026 season, and are graded against real results every week.</p>
  <div class="meta" id="meta"></div>
</header>

<h2>How well does it work?</h2>
<p class="sub">Backtest: each season from 2019 to 2024 predicted using only earlier seasons. 2026: the same predictions graded live.</p>
<div class="cards" id="scorecards"></div>

<h2>2026 predictions</h2>
<div class="tabs" role="tablist" id="tabs"></div>

<h3 style="margin:4px 0 10px;font-size:16px">Most likely to make a big leap</h3>
<div class="leaps" id="leaps"></div>

<div class="toolbar">
  <input id="search" type="search" placeholder="Search players or teams" aria-label="Search players or teams">
  <label><input type="checkbox" id="roleonly" checked> Players with a real role only</label>
</div>
<div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<p class="sub" style="margin-top:8px">Click a player to see what drives his prediction. PPG = PPR fantasy points per game.
Baseline = games-weighted PPG over 2024–2025.</p>

<h2>Live check: predicted vs. actual 2026 change</h2>
<p class="sub" id="livesub"></p>
<div class="chart" id="chart"><div class="tip" id="tip"></div></div>

<h2>Method</h2>
<div class="method"><ul id="method"></ul></div>

<footer>Built by Robert Dreyer. Data: nflverse (play-by-play, Next Gen Stats, depth charts, FTN charting),
Pro Football Reference via nflverse, OverTheCap contracts, FantasyPros consensus rankings archived by DynastyProcess.
<span id="repolink"></span></footer>
</div>

<script>
const DATA = __DATA__;
const POS = ["WR", "TE", "RB"];
const ROLE_FLOOR = {WR: 8, TE: 6, RB: 8};
const GROUP_NAMES = {track_record: "Track record", usage_efficiency: "Usage & efficiency", age_draft: "Age & draft capital",
  opportunity: "Next-season opportunity", team: "Team setting", health: "Health", coaching: "Coaching"};
let pos = "WR", sortKey = "pred", sortDir = -1, openRow = null;

const f1 = v => v == null ? "–" : v.toFixed(1);
const sgn = v => v == null ? "–" : Math.abs(v) < 0.05 ? "0.0" : (v > 0 ? "+" : "") + v.toFixed(1);
const pctf = v => v == null ? "–" : Math.round(v * 100) + "%";
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

// Header meta
document.getElementById("meta").innerHTML =
  `Updated ${DATA.updated}` + (DATA.throughWeek ? ` · 2026 results through Week ${DATA.throughWeek}` : "") +
  (DATA.repo ? ` · <a href="${DATA.repo}">Code and notebooks on GitHub</a>` : "");
if (DATA.repo) document.getElementById("repolink").innerHTML = ` <a href="${DATA.repo}">Source on GitHub</a>.`;

// Scorecards
const latestLive = {};
DATA.live.forEach(r => { if (!latestLive[r.position] || r.through_week >= latestLive[r.position].through_week) latestLive[r.position] = r; });
document.getElementById("scorecards").innerHTML = POS.map(p => {
  const b = DATA.backtest.find(x => x.position === p); const l = latestLive[p];
  const cls = v => Math.abs(v) < 0.05 ? "" : v > 0 ? "pos-up" : "pos-down";
  return `<div class="card"><h3>${p}s</h3>
    <div class="stat"><span>Backtest: model's top-10% risers</span><b class="${cls(b.top10pct_actual_change)}">${sgn(b.top10pct_actual_change)} PPG</b></div>
    <div class="stat"><span>Backtest: bottom 10%</span><b class="${cls(b.bottom10pct_actual_change)}">${sgn(b.bottom10pct_actual_change)} PPG</b></div>
    <div class="stat"><span>Avg miss vs. "repeat baseline"</span><b>${b.model_avg_miss_ppg.toFixed(2)} vs ${b.naive_avg_miss_ppg.toFixed(2)}</b></div>
    ${l ? `<div class="stat"><span>2026 (wk ${l.through_week}): top-20% predicted risers</span><b class="${cls(l.top20pct_pred_actual_change)}">${sgn(l.top20pct_pred_actual_change)} PPG</b></div>
    <div class="stat"><span>2026 (wk ${l.through_week}): everyone else</span><b class="${cls(l.others_actual_change)}">${sgn(l.others_actual_change)} PPG</b></div>` : ""}
  </div>`;
}).join("");

// Tabs
const tabs = document.getElementById("tabs");
tabs.innerHTML = POS.map(p => `<button role="tab" data-pos="${p}" aria-selected="${p === pos}">${p}</button>`).join("");
tabs.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
  pos = b.dataset.pos; openRow = null; tabs.querySelectorAll("button").forEach(x => x.setAttribute("aria-selected", x === b)); render(); });

// Table setup
const COLS = [
  {k: "name", l: "Player"}, {k: "team", l: "Team"}, {k: "qb", l: "2026 QB", sm: 1}, {k: "age", l: "Age", f: f1, sm: 1},
  {k: "base", l: "Baseline PPG", f: f1}, {k: "pred", l: "Predicted 2026", f: f1},
  {k: "chg", l: "Change", f: sgn}, {k: "leap", l: "Leap chance", f: pctf},
  {k: "rank", l: "Preseason rank", f: v => v == null ? "–" : pos + Math.round(v), sm: 1},
  {k: "ppg26", l: "2026 PPG so far", f: f1},
];
const thead = document.querySelector("#tbl thead"), tbody = document.querySelector("#tbl tbody");
thead.innerHTML = "<tr>" + COLS.map(c => `<th data-k="${c.k}" class="${c.sm ? "hide-sm" : ""}">${c.l}</th>`).join("") + "</tr>";
thead.addEventListener("click", e => { const th = e.target.closest("th"); if (!th) return;
  const k = th.dataset.k; sortDir = (k === sortKey) ? -sortDir : (k === "name" || k === "team" || k === "qb" || k === "rank" || k === "age" ? 1 : -1);
  sortKey = k; renderTable(); });
document.getElementById("search").addEventListener("input", renderTable);
document.getElementById("roleonly").addEventListener("change", renderTable);
tbody.addEventListener("click", e => { const tr = e.target.closest("tr.row"); if (!tr) return;
  openRow = openRow === tr.dataset.name ? null : tr.dataset.name; renderTable(); });

function whyHTML(p) {
  const entries = Object.entries(p.push).filter(([, v]) => v != null);
  const max = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));
  const rows = entries.map(([g, v]) => {
    const w = Math.abs(v) / max * 50, left = v >= 0 ? 50 : 50 - w;
    return `<div class="lbl">${GROUP_NAMES[g] || g} <span style="color:var(--ink-3)">${sgn(v)}</span></div>
      <div class="bar"><div class="mid"></div><div class="fill" style="left:${left}%;width:${w}%;background:${v >= 0 ? "var(--up)" : "var(--down)"}"></div></div>`;
  }).join("");
  return `<div class="why">${rows}</div><div class="why-note">How much each group of factors pushes his predicted change, in PPG,
    compared with an average ${p.pos} in the model. Blue raises the prediction, red lowers it.</div>`;
}

function renderTable() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const role = document.getElementById("roleonly").checked;
  let rows = DATA.players.filter(p => p.pos === pos && (!role || p.base >= ROLE_FLOOR[pos])
    && (!q || p.name.toLowerCase().includes(q) || (p.team || "").toLowerCase().includes(q) || (p.qb || "").toLowerCase().includes(q)));
  rows.sort((a, b) => { const x = a[sortKey], y = b[sortKey];
    if (x == null) return 1; if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir; });
  thead.querySelectorAll("th").forEach(th => th.setAttribute("aria-sort", th.dataset.k === sortKey ? (sortDir < 0 ? "descending" : "ascending") : "none"));
  tbody.innerHTML = rows.length ? rows.map(p => {
    const cells = COLS.map(c => { let v = c.f ? c.f(p[c.k]) : esc(p[c.k] || "–");
      if (c.k === "chg") v = `<span class="${p.chg >= 0 ? "pos-up" : "pos-down"}">${v}</span>`;
      if (c.k === "ppg26" && p.ppg26 != null) v += ` <span style="color:var(--ink-3)">(${p.g26}g)</span>`;
      return `<td class="${c.sm ? "hide-sm" : ""}">${v}</td>`; }).join("");
    const row = `<tr class="row" data-name="${esc(p.name)}" aria-expanded="${openRow === p.name}">${cells}</tr>`;
    return openRow === p.name ? row + `<tr class="detail"><td colspan="${COLS.length}">${whyHTML(p)}</td></tr>` : row;
  }).join("") : `<tr><td colspan="${COLS.length}" class="empty">No players match.</td></tr>`;
}

function renderLeaps() {
  const top = DATA.players.filter(p => p.pos === pos).sort((a, b) => b.leap - a.leap).slice(0, 6);
  document.getElementById("leaps").innerHTML = top.map(p => {
    const chips = [...(p.up ? p.up.split("; ").slice(0, 3).map(t => `<span class="chip up">${esc(t)}</span>`) : []),
                   ...(p.down ? p.down.split("; ").slice(0, 1).map(t => `<span class="chip down">${esc(t)}</span>`) : [])].join("");
    return `<div class="leap"><div class="top"><span class="nm">${esc(p.name)} <span class="tm">${esc(p.team || "")}</span></span>
      <span class="pct">${pctf(p.leap)}</span></div>
      <div class="nums"><span>Baseline <b>${f1(p.base)}</b></span><span>Predicted <b>${f1(p.pred)}</b></span>
      ${p.ppg26 != null ? `<span>2026 so far <b>${f1(p.ppg26)}</b></span>` : ""}
      ${p.rank != null ? `<span>Preseason <b>${pos}${Math.round(p.rank)}</b></span>` : ""}</div>
      <div class="chips">${chips}</div></div>`;
  }).join("");
}

function renderChart() {
  const pts = DATA.players.filter(p => p.pos === pos && p.g26 >= 2 && p.ppg26 != null)
    .map(p => ({n: p.name, x: p.chg, y: p.ppg26 - p.base}));
  const box = document.getElementById("chart"), tip = document.getElementById("tip");
  box.querySelectorAll("svg").forEach(s => s.remove());
  const sub = document.getElementById("livesub");
  if (pts.length < 5) { sub.textContent = "Appears once 2026 games are graded (run grade_2026.py)."; return; }
  const n = pts.length, mx = pts.reduce((s, p) => s + p.x, 0) / n, my = pts.reduce((s, p) => s + p.y, 0) / n;
  const r = pts.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0) /
    Math.sqrt(pts.reduce((s, p) => s + (p.x - mx) ** 2, 0) * pts.reduce((s, p) => s + (p.y - my) ** 2, 0));
  sub.textContent = `Each dot is a ${pos} with 2+ games in 2026 (n = ${n}). Correlation so far: ${r.toFixed(2)}. ` +
    `Early-season results are noisy; this firms up after about 8 games.`;
  const W = 760, H = 380, m = {l: 48, r: 16, t: 14, b: 40};
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const x0 = Math.min(-3, ...xs) - .5, x1 = Math.max(3, ...xs) + .5, y0 = Math.min(-6, ...ys) - 1, y1 = Math.max(6, ...ys) + 1;
  const X = v => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), Y = v => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  const ticks = (a, b, step) => { const t = []; for (let v = Math.ceil(a / step) * step; v <= b; v += step) t.push(v); return t; };
  let g = "";
  ticks(y0, y1, 4).forEach(v => g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${v > 0 ? "+" : ""}${v}</text>`);
  ticks(x0, x1, 1).forEach(v => g += `<text x="${X(v)}" y="${H - m.b + 16}" text-anchor="middle">${v > 0 ? "+" : ""}${v}</text>`);
  g += `<line x1="${X(0)}" x2="${X(0)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--ink-3)" stroke-width="1"/>`;
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--ink-3)" stroke-width="1"/>`;
  const lo = Math.max(x0, y0), hi = Math.min(x1, y1);
  g += `<line x1="${X(lo)}" y1="${Y(lo)}" x2="${X(hi)}" y2="${Y(hi)}" stroke="var(--pred)" stroke-width="2" stroke-dasharray="5 4"/>`;
  g += pts.map((p, i) => `<circle data-i="${i}" cx="${X(p.x)}" cy="${Y(p.y)}" r="5" fill="var(--accent)" fill-opacity=".75" stroke="var(--surface)" stroke-width="1.5"/>`).join("");
  g += `<text x="${(W + m.l) / 2}" y="${H - 6}" text-anchor="middle">Predicted change vs. baseline (PPG)</text>`;
  g += `<text transform="translate(12 ${(H - m.b + m.t) / 2}) rotate(-90)" text-anchor="middle">Actual 2026 change (PPG)</text>`;
  box.insertAdjacentHTML("afterbegin", `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Scatter plot of predicted versus actual change in fantasy points per game for ${pos}s in 2026">${g}</svg>
    <div class="legend"><span><span class="dot" style="background:var(--accent)"></span>Player</span>
    <span><span class="dot" style="background:var(--pred)"></span>Dashed line = prediction exactly right</span></div>`);
  const svg = box.querySelector("svg");
  svg.addEventListener("mousemove", e => { const c = e.target.closest("circle");
    if (!c) { tip.style.opacity = 0; return; } const p = pts[+c.dataset.i], rb = box.getBoundingClientRect();
    tip.textContent = `${p.n}: predicted ${sgn(p.x)}, actual ${sgn(p.y)}`; tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX - rb.left + 12, rb.width - tip.offsetWidth - 8) + "px"; tip.style.top = (e.clientY - rb.top - 30) + "px"; });
  svg.addEventListener("mouseleave", () => tip.style.opacity = 0);
}

// Method
const repo = DATA.repo;
const nb = n => repo ? `<a href="${repo}/blob/main/notebooks/${n}">${n}</a>` : n;
document.getElementById("method").innerHTML = [
  `<b>Baseline:</b> a player's PPR points per game over his last two seasons, weighted by games played.`,
  `<b>Change model:</b> ridge regression predicting next season's PPG minus that baseline, from ~25 factors per position: track record, per-route efficiency, usage, red-zone role, age and draft capital, depth chart, targets and carries vacated by departed teammates, QB play, blocking and schedule.`,
  `<b>Leap model:</b> logistic regression for the chance of a big leap (WR/RB: +4 PPG and 14+ PPG; TE: +3 and 11+).`,
  `<b>Honest testing:</b> each season from 2019 to 2024 is predicted with a model trained only on earlier seasons. The 2026 predictions use data through the 2025 season plus preseason depth charts and rankings, never 2026 results.`,
  `<b>Biggest drivers:</b> regression to the mean (high baselines fall), youth and draft capital, efficiency per route run, and opportunity: depth-chart role and vacated targets or carries.`,
  `<b>Walkthroughs:</b> ${nb("wr_jump_model.ipynb")}, ${nb("rb_jump_model.ipynb")}, ${nb("te_jump_model.ipynb")}, ${nb("wr_breakouts.ipynb")}.`,
].map(t => `<li>${t}</li>`).join("");

function render() { renderLeaps(); renderTable(); renderChart(); }
render();
</script>
</body>
</html>
"""

(SITE / "index.html").write_text(HTML.replace("__DATA__", json.dumps(data)), encoding="utf-8")
(SITE / ".nojekyll").write_text("")
print(f"Built {SITE / 'index.html'} ({len(players)} players"
      + (f", 2026 results through week {through_week})" if through_week else ")"))
