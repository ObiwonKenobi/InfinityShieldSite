#!/usr/bin/env python3
"""
Build /obi-wan/: a plain page on what the agents do and what they have done.

Numbers come from three places: files already in this repo (the brief and the archive),
git history, and obi-wan/data/stats.json, which holds the agent list, the session tracker
totals, and the feeds from machines that report their own numbers (null until connected).
Nothing on the page names hosts, addresses, ports, or what an agent can reach.

Usage (from the repo root):  python3 tools/build_obiwan.py
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import ROOT, esc, head, nav  # noqa: E402
import charts  # noqa: E402

DATA = ROOT / "obi-wan" / "data" / "stats.json"
OUT = ROOT / "obi-wan" / "index.html"
CATS = [("vulns", "Vulnerabilities"), ("supply", "Supply chain"), ("breaches", "Breaches"), ("other", "Law enforcement, research"), ("outages", "Outages, no attack")]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def gather():
    cur = json.loads((ROOT / "brief" / "data" / "current.json").read_text(encoding="utf-8"))
    months = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "archive" / "data").glob("*.json"))]
    kev_path = ROOT / "brief" / "data" / "kev.json"
    kev = json.loads(kev_path.read_text(encoding="utf-8")) if kev_path.exists() else {}
    refreshes = len([l for l in git("log", "--format=%s").splitlines() if l.startswith("Rolling brief: refresh")])
    return {
        "cur": cur, "months": months, "kev": kev, "refreshes": refreshes,
        "commits": int(git("rev-list", "--count", "HEAD") or 0),
    }


def count_items(d):
    return {k: len(d.get(k, [])) for k, _ in CATS}


def section(sid, title, body):
    return f'  <section aria-labelledby="{sid}">\n    <h2 id="{sid}">{esc(title)}</h2>\n{body}\n  </section>'


def build(s, g):
    cur, months, kev = g["cur"], g["months"], g["kev"]
    cur_n = count_items(cur)
    cur_total = sum(cur_n.values()) + len(cur["top"])
    arch_total = sum(sum(count_items(m).values()) + len(m.get("top", [])) for m in months)
    running = sum(1 for a in s["agents"] if a["status"] == "Running")
    paused = sum(1 for a in s["agents"] if a["status"] == "Paused")
    waiting = sum(1 for a in s["agents"] if a["status"] == "Needs a feed")
    cpe = s["cpe"]
    secured = cpe["claimed_cpe"] + cpe["watched_cpe"]
    planned = secured + cpe["remaining_cpe"]
    chg = cur.get("changes", {})

    glance = charts.kpi_row([
        ("Agents running", str(running), f"{paused} paused, {waiting} waiting for a feed"),
        ("Brief refreshes published", str(g["refreshes"]), "weekly, since late October"),
        ("Items in the current brief", str(cur_total), f'{cur["period"]}'),
        ("Items in the archive", str(arch_total), f"{len(months)} calendar months"),
        ("Session credits secured", f"{secured:g}", f'of {planned:g} planned'),
    ])

    agents = ['    <ul class="list">']
    for a in s["agents"]:
        tag = a["status"] + (f' · {a["cadence"]}' if a["cadence"] else "")
        agents.append(f'      <li><span class="label">{esc(a["name"])}</span><div class="outage-body"><p class="basis">{esc(tag)}</p><p>{esc(a["does"])}</p></div></li>')
    agents.append("    </ul>")

    brief_rows = sorted(((n, cur_n[k], f"{n}: {cur_n[k]}") for k, n in CATS), key=lambda r: -r[1])
    arch_rows = [(m["label"], sum(count_items(m).values()) + len(m.get("top", [])), f'{m["label"]}: items') for m in months]
    brief_body = "\n".join([
        charts.kpi_row([
            ("Exploited vulnerabilities", str(cur_n["vulns"]), "in the current table"),
            ("CISA KEV entries tracked", str(len(kev.get("entries", []))), "kept for the last 180 days"),
            ("Added this week", str(len(chg.get("added", []))), f'since {chg.get("since", "the last run")}'),
            ("Updated this week", str(len(chg.get("updated", []))), ""),
        ]),
        '    <div class="viz-row">',
        charts.ranked_bars(brief_rows, "Current brief by category", ""),
        charts.ranked_bars(arch_rows, "Archive items by month", ""),
        "    </div>",
    ])

    cpe_body = "\n".join([
        charts.kpi_row([
            ("On the transcript", f'{cpe["claimed_cpe"]:g}', f'{cpe["claimed_sessions"]} sessions already claimed'),
            ("Watched, ready to claim", f'{cpe["watched_cpe"]:g}', f'{cpe["watched_sessions"]} sessions checked off'),
            ("Still to do", f'{cpe["remaining_cpe"]:g}', f'{cpe["remaining_sessions"]} sessions left'),
        ]),
        charts.meter(secured, planned, "Credits secured of those planned", f'reporting deadline {cpe["deadline"]}'),
    ])

    def feed(name, data):
        if data:
            return None
        return f'<li><span class="label">{esc(name)}</span><div class="outage-body"><p class="basis">No feed connected yet</p><p>This machine reports its own numbers. Until it does, this page shows nothing rather than a guess.</p></div></li>'

    pending = [x for x in (feed("Job watch", s["feeds"].get("jobwatch")), feed("Game server", s["feeds"].get("minecraft"))) if x]
    feeds_body = ('    <ul class="list">\n      ' + "\n      ".join(pending) + "\n    </ul>") if pending else ""

    how = (
        "    <p>The threat brief numbers are counted from the same files that build the brief and archive pages, and the refresh count comes from the repository history. "
        "The session figures come from the tracking spreadsheet and are updated by hand in this page's data file. Machines that cannot be reached from the cloud, such as the game server and job watch, "
        "write a small stats file on their own schedule and this page is rebuilt from it. Nothing here names hostnames, addresses or ports, or what any agent is able to reach.</p>"
    )

    parts = [
        head("Obi-Wan | Infinity Shield", "What the agents do and what they have done, with the numbers."),
        nav("obi-wan"),
        '<main id="main" class="wrap">',
        "  <header>",
        f'    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>Agents and automation</span><span>As of {esc(s["as_of"])}</span></div>',
        "    <h1>Obi-Wan <span>at work</span></h1>",
        '    <p class="lede">A plain account of the agents that run in the background, what each one does, and the numbers behind what they have produced so far.</p>',
        "  </header>",
        "",
        section("glance", "At a glance", glance),
        "",
        section("agents", "What each agent does", "\n".join(agents)),
        "",
        section("brief", "The threat brief", brief_body),
        "",
        section("sessions", "Conference sessions and credits", cpe_body),
        "",
        *([section("feeds", "Waiting for numbers", feeds_body), ""] if feeds_body else []),
        section("how", "Where these numbers come from", how),
        "",
        f'  <footer>Counted from the brief, archive and repository history as of {esc(s["as_of"])}. · <a href="/brief/">Current brief</a> · <a href="/archive/">Archive</a> · <a href="/">Home</a></footer>',
        "</main>",
        "",
        "</body>",
        "</html>",
    ]
    html = "\n".join(parts) + "\n"
    # Unlisted: kept out of search engines. Remove this line to let it be indexed.
    return html.replace('<meta name="referrer"', '<meta name="robots" content="noindex, nofollow">\n<meta name="referrer"', 1)


def main():
    s = json.loads(DATA.read_text(encoding="utf-8"))
    OUT.write_text(build(s, gather()), encoding="utf-8")
    print("built obi-wan/index.html")


if __name__ == "__main__":
    main()
