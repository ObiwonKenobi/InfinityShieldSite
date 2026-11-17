#!/usr/bin/env python3
"""
Build /obiwon/: a record of what Obiwon, Chris's AI assistant, has built and done.

Counts come from files in this repo, git history (commits Claude authored here), and
obiwon/data/stats.json (the agent list, the EQEmu dashboard repo as counted on a clone, the
session tracker totals, and optional `blackout` and `jobs` sections that render only when
present). Nothing here names hostnames, addresses or ports, or what any agent can reach.

Usage (from the repo root):  python3 tools/build_obiwon.py
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import ROOT, esc, head, nav  # noqa: E402
import charts  # noqa: E402

DATA = ROOT / "obiwon" / "data" / "stats.json"
OUT = ROOT / "obiwon" / "index.html"
CATS = [("vulns", "Vulnerabilities"), ("supply", "Supply chain"), ("breaches", "Breaches"), ("other", "Law enforcement, research"), ("outages", "Outages, no attack")]
SHOTS = [
    ("screenshot-overview.png", "The dashboard overview with navigation tabs and a summary of GM activity."),
    ("screenshot-highlights.png", "The summary highlights view: top kills, top items given, top recipients and peak hours."),
    ("screenshot-trends.png", "The trends view: an activity heatmap by day and hour and a session timeline."),
    ("screenshot-kills-items.png", "The kills and items log with rarity colors and item lookups."),
]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def n_items(d):
    return sum(len(d.get(k, [])) for k, _ in CATS) + len(d.get("top", []))


def lines_of(paths):
    total = 0
    for p in paths:
        f = ROOT / p
        if f.exists():
            total += len(f.read_text(encoding="utf-8").splitlines())
    return total


def weekly(dates, first, last):
    start = first - dt.timedelta(first.weekday())
    out = []
    while start <= last:
        end = start + dt.timedelta(6)
        out.append({"start": start, "end": end, "count": sum(1 for d in dates if start <= d <= end)})
        start = end + dt.timedelta(1)
    return out


def fmt_day(d):
    return f"{d.day} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.month - 1]}"


def section(sid, title, body, intro=""):
    p = f'    <p>{intro}</p>\n' if intro else ""
    return f'  <section aria-labelledby="{sid}">\n    <h2 id="{sid}">{esc(title)}</h2>\n{p}{body}\n  </section>'


def build(s):
    cur = json.loads((ROOT / "brief" / "data" / "current.json").read_text(encoding="utf-8"))
    months = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "archive" / "data").glob("*.json"))]
    claude_dates = [dt.date.fromisoformat(x) for x in git("log", "--author=Claude", "--format=%ad", "--date=short").splitlines() if x]
    claude_commits = len(claude_dates)
    refreshes = len([l for l in git("log", "--format=%s").splitlines() if l.startswith("Rolling brief: refresh")])
    pages = 5 + len(months)  # home, about, brief, archive index, this page, plus each month
    site_lines = lines_of([str(p.relative_to(ROOT)) for p in (ROOT / "tools").glob("*.py")] + ["brief.css"])
    eq = s["eq"]
    eq_lines = sum(eq["lines"].values())
    brief_items, arch_items = n_items(cur), sum(n_items(m) for m in months)
    cpe = s["cpe"]
    secured = cpe["claimed_cpe"] + cpe["watched_cpe"]
    planned = secured + cpe["remaining_cpe"]

    glance = charts.kpi_row([
        ("Projects built", "4", "dashboard, threat brief, agents, session tracker"),
        ("Commits written here", str(claude_commits), "in the Infinity Shield repo"),
        ("Lines of code", f"{eq_lines + site_lines:,}", "EQ dashboard plus the brief tooling"),
        ("Pages published", str(pages), "home, brief, archive, timeline views and more"),
        ("Threat items tracked", str(brief_items + arch_items), f"{len(months) + 1} briefs, {refreshes} refreshes"),
    ])

    shots = "\n".join(f'      <figure class="shot"><img src="/obiwon/img/{f}" alt="{esc(a)}" loading="lazy"></figure>' for f, a in SHOTS)
    eq_body = "\n".join([
        charts.kpi_row([
            ("Lines of code", f"{eq_lines:,}", "code and Docker config"),
            ("Commits", str(eq["commits"]), f'{eq["first"]} to {eq["last"]}'),
            ("Views", str(len(eq["views"])), ", ".join(eq["views"][:3]) + " and more"),
            ("Containers", "1", "Docker and Compose, with a host export daemon"),
        ]),
        '    <p>A real-time GM activity dashboard for an EQEmu server, run in Docker on Blackout. It tracks GM commands, item grants, kills, player deaths, bot activity, level progression, character status and the Spire audit log through a dark-themed web page.</p>',
        '    <p>The second version fixed a duplicate class and race table that was silently shadowing the correct one, added optional token authentication, moved the database password off the command line, added a single-instance lock and a health check for the web process, a Discord alert for new commands, a SQLite history that survives log truncation, and change detection that skips the build when nothing changed, which brings idle CPU near zero. It is released under the MIT license.</p>',
        '    <div class="shots">', shots, '    </div>',
    ])

    brief_rows = sorted(((n, len(cur.get(k, [])), f"{n}: {len(cur.get(k, []))}") for k, n in CATS), key=lambda r: -r[1])
    arch_rows = [(m["label"], n_items(m), f'{m["label"]}: items') for m in months]
    chg = cur.get("changes", {})
    brief_body = "\n".join([
        '    <p>A rolling 30 day cybersecurity brief refreshed every Monday, plus a calendar-month archive. Each run researches primary sources, checks the numbers, rebuilds the pages and publishes with no review step, behind validation that refuses to publish on a bad build. It also draws a day by day timeline, a weekly month by month view across the archive, a New this week section, and charts with a text version of every figure. The whole site was passed through an accessibility audit to WCAG 2.1 and 2.2 AA with the dark theme kept.</p>',
        charts.kpi_row([
            ("Items in the current brief", str(brief_items), cur["period"]),
            ("Items in the archive", str(arch_items), f"{len(months)} months"),
            ("Added this week", str(len(chg.get("added", []))), f'since {chg.get("since", "the last run")}'),
            ("Primary source hosts", "13", "SEC, DOJ, Treasury, CERTs and more"),
        ]),
        '    <div class="viz-row">',
        charts.ranked_bars(brief_rows, "Current brief by category", ""),
        charts.ranked_bars(arch_rows, "Archive items by month", ""),
        '    </div>',
        charts.columns(weekly([d for d in claude_dates if d >= dt.date(2026, 10, 26)], dt.date(2026, 10, 26), max(claude_dates)), "Commits written per week in this repo", lambda b: f'{fmt_day(b["start"])} to {fmt_day(b["end"])}'),
    ])

    agents = ['    <ul class="list">']
    for a in s["agents"]:
        tag = a["status"] + (f' · {a["cadence"]}' if a["cadence"] else "")
        agents.append(f'      <li><span class="label">{esc(a["name"])}</span><div class="outage-body"><p class="basis">{esc(tag)}</p><p>{esc(a["does"])}</p></div></li>')
    agents.append("    </ul>")

    cpe_body = "\n".join([
        charts.kpi_row([
            ("On the transcript", f'{cpe["claimed_cpe"]:g}', f'{cpe["claimed_sessions"]} sessions already claimed'),
            ("Watched, ready to claim", f'{cpe["watched_cpe"]:g}', f'{cpe["watched_sessions"]} sessions checked off'),
            ("Still to do", f'{cpe["remaining_cpe"]:g}', f'{cpe["remaining_sessions"]} sessions left'),
        ]),
        charts.meter(secured, planned, "Credits secured of those planned", f'reporting deadline {cpe["deadline"]}'),
    ])

    extras = []
    for key, title in (("blackout", "On Blackout"), ("jobs", "Job search")):
        sec = s.get(key)
        if sec:
            tiles = [(t["label"], str(t["value"]), t.get("sub", "")) for t in sec.get("tiles", [])]
            body = charts.kpi_row(tiles) + "".join(f'\n    <p>{esc(x)}</p>' for x in sec.get("notes", []))
            extras += [section(key, title, body), ""]

    how = ('    <p>Commit counts come from the repository history, using the commits written by the assistant. Lines of code are counted from the files. '
           "The EQ dashboard figures were counted on a clone of its repository on the date shown. The session figures come from the tracking spreadsheet. "
           "Nothing here names hostnames, addresses or ports, or what any agent is able to reach.</p>")

    parts = [
        head("Obiwon | Infinity Shield", "Everything Obiwon, an AI assistant, has built and done, with the numbers."),
        nav("obiwon"),
        '<main id="main" class="wrap">',
        "  <header>",
        f'    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>AI assistant</span><span>As of {esc(s["as_of"])}</span></div>',
        "    <h1>Obiwon <span>at work</span></h1>",
        '    <p class="lede">Obiwon is the AI assistant that works with Chris Opp. This is a running record of what it has built and done, counted from the code, the commit history and the scheduled work.</p>',
        "  </header>",
        "",
        section("glance", "At a glance", glance),
        "",
        section("eq", "EQEmu GM Dashboard", eq_body),
        "",
        section("brief", "Infinity Shield threat brief", brief_body),
        "",
        *extras,
        section("agents", "The agents", "\n".join(agents)),
        "",
        section("sessions", "Conference sessions and credits", cpe_body),
        "",
        section("how", "Where these numbers come from", how),
        "",
        f'  <footer>Counted as of {esc(s["as_of"])}. · <a href="/brief/">Current brief</a> · <a href="/archive/">Archive</a> · <a href="/">Home</a></footer>',
        "</main>",
        "",
        "</body>",
        "</html>",
    ]
    html = "\n".join(parts) + "\n"
    return html.replace('<meta name="referrer"', '<meta name="robots" content="noindex, nofollow">\n<meta name="referrer"', 1)


def main():
    s = json.loads(DATA.read_text(encoding="utf-8"))
    OUT.write_text(build(s), encoding="utf-8")
    print("built obiwon/index.html")


if __name__ == "__main__":
    main()
