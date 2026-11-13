#!/usr/bin/env python3
"""
Build flock/index.html from flock/data/history.json.

Plain HTML and inline SVG, no scripts (the site's content security policy
allows none). Every chart has a table twin. With no snapshots the page says so
and shows no numbers.

Usage (from the repo root):
  python3 tools/build_flock.py
  python3 tools/build_flock.py --data PATH --out PATH   build from another file, for testing
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import ROOT, esc, head, nav  # noqa: E402
from charts import kpi_row  # noqa: E402
from collect_flock import AREAS as DEFAULT_AREAS  # noqa: E402

DATA = ROOT / "flock" / "data" / "history.json"
OUT = ROOT / "flock" / "index.html"

AREAS_CITY = (41.07, -104.95, 41.24, -104.65)
W, H = 720, 300
PAD_L, PAD_R, PAD_T, PAD_B = 46, 16, 14, 34

STYLE = """<style>
.flock-fig { margin: 0; min-width: 0; }
.flock-fig figcaption { font-size: .8rem; color: var(--muted); margin-bottom: 10px; }
.flock-svg { width: 100%; height: auto; display: block; background: var(--bg1); border: 1px solid var(--border); }
.flock-svg text { fill: var(--muted); font-family: var(--mono); font-size: 11px; }
.flock-svg .grid { stroke: var(--rule); stroke-width: 1; }
.flock-svg .axis { stroke: var(--faint); stroke-width: 1; }
.flock-svg .ln-county { fill: none; stroke: var(--accent); stroke-width: 2.5; }
.flock-svg .ln-city { fill: none; stroke: var(--high); stroke-width: 2.5; stroke-dasharray: 6 4; }
.flock-svg .dot-county { fill: var(--accent); }
.flock-svg .dot-city { fill: var(--high); }
.flock-svg .add { fill: var(--accent); }
.flock-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 10px; font-size: .78rem; color: var(--muted); }
.flock-legend i { display: inline-block; width: 18px; height: 0; border-top: 2.5px solid var(--accent); vertical-align: middle; margin-right: 6px; }
.flock-legend i.d { border-top: 2.5px dashed var(--high); }
.flock-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
.flock-table th, .flock-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); }
.flock-table th { font-family: var(--mono); font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: var(--faint); font-weight: 500; }
.flock-table td.n { text-align: right; font-variant-numeric: tabular-nums; }
.flock-note { font-size: .82rem; color: var(--muted); border-left: 2px solid var(--rule); padding-left: 14px; }
.flock-empty { background: var(--bg1); border: 1px solid var(--border); padding: 18px; color: var(--muted); }
details.flock-data { font-size: .82rem; }
details.flock-data summary { cursor: pointer; color: var(--muted); margin-bottom: 10px; }
.scroll-x { overflow-x: auto; }
.flock-map { width: 100%; height: auto; display: block; background: var(--bg1); border: 1px solid var(--border); }
.flock-map text { fill: var(--faint); font-family: var(--mono); font-size: 10px; }
.flock-map .frame { fill: none; stroke: var(--faint); stroke-width: 1; }
.flock-map .box { fill: none; stroke: var(--high); stroke-width: 1; stroke-dasharray: 4 3; }
.flock-map .pt { fill: var(--accent); fill-opacity: .85; }
.flock-map .pt.city { fill: var(--high); }
.flock-map .new { fill: none; stroke: var(--text); stroke-width: 1.5; }
.flock-links { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: .82rem; margin-top: 10px; }
.flock-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.flock-list li { display: grid; grid-template-columns: 96px 1fr; gap: 4px 16px; font-size: .88rem; }
.flock-list .when { font-family: var(--mono); font-size: .72rem; letter-spacing: .06em; color: var(--faint); padding-top: 3px; }
.flock-list .who { color: var(--muted); font-size: .78rem; }
@media (max-width: 520px) { .flock-list li { grid-template-columns: 1fr; } }
</style>"""


def d(s):
    return dt.date.fromisoformat(s)


def series(hist):
    """Per snapshot: date, county count, city count, new ids since the previous snapshot."""
    out, prev = [], set()
    for s in hist["snapshots"]:
        cur = set(s["county"])
        out.append({
            "date": s["date"], "county": len(s["county"]), "city": len(s["city"]),
            "added": len(cur - prev), "removed": len(prev - cur), "source": s.get("source", ""),
            "alpr_total": s.get("alpr_total"),
        })
        prev = cur
    return out


def first_seen(hist):
    seen = {}
    for s in hist["snapshots"]:
        for i in s["county"]:
            seen.setdefault(i, s["date"])
    return seen


def nice_max(v):
    if v <= 5:
        return 5
    step = 10 ** (len(str(int(v))) - 1)
    for m in (1, 2, 2.5, 5, 10):
        if m * step >= v:
            return int(m * step)
    return int(v)


def x_scale(dates):
    lo, hi = d(dates[0]), d(dates[-1])
    span = max((hi - lo).days, 1)
    return lambda s: PAD_L + (d(s) - lo).days / span * (W - PAD_L - PAD_R)


def y_scale(top):
    return lambda v: PAD_T + (1 - v / top) * (H - PAD_T - PAD_B)


def axes(dates, top, y):
    out = []
    for k in range(5):
        v = top * k / 4
        out.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{int(v)}</text>')
    x = x_scale(dates)
    out.append(f'<line class="axis" x1="{PAD_L}" x2="{W - PAD_R}" y1="{H - PAD_B}" y2="{H - PAD_B}"/>')
    ticks = sorted({dates[0], dates[-1], dates[len(dates) // 2]})
    for t in ticks:
        anchor = "start" if t == dates[0] and len(ticks) > 1 else ("end" if t == dates[-1] and len(ticks) > 1 else "middle")
        out.append(f'<text x="{x(t):.1f}" y="{H - PAD_B + 18}" text-anchor="{anchor}">{esc(t)}</text>')
    return "\n".join(out)


def line_chart(rows):
    dates = [r["date"] for r in rows]
    top = nice_max(max(r["county"] for r in rows))
    x, y = x_scale(dates) if len(rows) > 1 else (lambda s: PAD_L + (W - PAD_L - PAD_R) / 2), y_scale(top)
    pts = lambda key: " ".join(f"{x(r['date']):.1f},{y(r[key]):.1f}" for r in rows)
    dots = "".join(
        f'<circle class="dot-county" cx="{x(r["date"]):.1f}" cy="{y(r["county"]):.1f}" r="3"><title>{esc(r["date"])}: {r["county"]} in the county box</title></circle>'
        f'<circle class="dot-city" cx="{x(r["date"]):.1f}" cy="{y(r["city"]):.1f}" r="3"><title>{esc(r["date"])}: {r["city"]} in the Cheyenne box</title></circle>'
        for r in rows
    )
    lines = ""
    if len(rows) > 1:
        lines = f'<polyline class="ln-county" points="{pts("county")}"/><polyline class="ln-city" points="{pts("city")}"/>'
    label = f"Flock cameras mapped over time. Latest {rows[-1]['date']}: {rows[-1]['county']} in Laramie County, {rows[-1]['city']} in Cheyenne."
    return (
        '<figure class="flock-fig"><figcaption>Cameras mapped, by snapshot date</figcaption>'
        f'<svg class="flock-svg" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
        f'{axes(dates, top, y)}{lines}{dots}</svg>'
        '<div class="flock-legend"><span><i></i>Laramie County (bounding box)</span>'
        '<span><i class="d"></i>Cheyenne area (bounding box)</span></div></figure>'
    )


def add_chart(rows):
    if len(rows) < 2:
        return ""
    steps = rows[1:]
    top = nice_max(max(max(r["added"] for r in steps), 1))
    y = y_scale(top)
    n = len(steps)
    slot = (W - PAD_L - PAD_R) / n
    bw = max(min(slot * 0.7, 40), 2)
    bars = []
    for k, r in enumerate(steps):
        cx = PAD_L + slot * (k + 0.5)
        h = (H - PAD_B) - y(r["added"])
        bars.append(
            f'<rect class="add" x="{cx - bw / 2:.1f}" y="{y(r["added"]):.1f}" width="{bw:.1f}" height="{max(h, 0):.1f}">'
            f'<title>to {esc(r["date"])}: {r["added"]} added, {r["removed"]} removed</title></rect>'
        )
    gridl = []
    for k in range(5):
        v = top * k / 4
        gridl.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        gridl.append(f'<text x="{PAD_L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{int(v)}</text>')
    gridl.append(f'<line class="axis" x1="{PAD_L}" x2="{W - PAD_R}" y1="{H - PAD_B}" y2="{H - PAD_B}"/>')
    for pos in sorted({0, n // 2, n - 1}):
        cx = PAD_L + slot * (pos + 0.5)
        gridl.append(f'<text x="{cx:.1f}" y="{H - PAD_B + 18}" text-anchor="middle">{esc(steps[pos]["date"])}</text>')
    label = "Cameras newly mapped between snapshots in Laramie County. " + ", ".join(f'{r["date"]}: {r["added"]}' for r in steps[-6:])
    return (
        '<figure class="flock-fig"><figcaption>Newly mapped since the previous snapshot (county box)</figcaption>'
        f'<svg class="flock-svg" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">{"".join(gridl)}{"".join(bars)}</svg></figure>'
    )


def table_snapshots(rows):
    body = "".join(
        f'<tr><td>{esc(r["date"])}</td><td class="n">{r["county"]}</td><td class="n">{r["city"]}</td>'
        f'<td class="n">{r["added"]}</td><td class="n">{r["removed"]}</td><td>{esc(r["source"].replace("overpass-", ""))}</td></tr>'
        for r in reversed(rows)
    )
    return (
        '<details class="flock-data"><summary>Snapshot table</summary><div class="scroll-x"><table class="flock-table">'
        '<thead><tr><th>Snapshot</th><th>County</th><th>Cheyenne</th><th>Added</th><th>Removed</th><th>Source</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div></details>'
    )


def table_recent(hist, rows):
    seen = first_seen(hist)
    first = hist["snapshots"][0]["date"]
    city_ids = set(hist["snapshots"][-1]["city"])
    latest = set(hist["snapshots"][-1]["county"])
    new = [(i, dte) for i, dte in seen.items() if dte != first and i in latest]
    new.sort(key=lambda t: (t[1], int(t[0])), reverse=True)
    if not new:
        return ""
    body = "".join(
        f'<tr><td>{esc(dte)}</td><td>{"Cheyenne area" if i in city_ids else "Rest of county"}</td>'
        f'<td><a href="https://www.openstreetmap.org/node/{esc(i)}" rel="noopener noreferrer">node {esc(i)}</a></td></tr>'
        for i, dte in new[:20]
    )
    return (
        '<section><h2>Recently mapped</h2>'
        '<p class="flock-note" style="margin-bottom:14px">Date is the first snapshot a camera appears in, so it is the latest it could have been mapped, not the date it was installed.</p>'
        '<div class="scroll-x"><table class="flock-table"><thead><tr><th>First seen by</th><th>Area</th><th>OpenStreetMap</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div></section>'
    )


def dot_map(bbox, pts, new_ids, caption, width=520, r=3):
    """Static point map: lon/lat scaled by cos(latitude), no basemap. pts: [(id, lat, lon, in_city)]."""
    south, west, north, east = bbox
    k = math.cos(math.radians((south + north) / 2))
    ww, hh = (east - west) * k, north - south
    pad = 8
    w = width
    h = round(w * hh / ww)
    X = lambda lon: pad + (lon - west) / (east - west) * (w - 2 * pad)
    Y = lambda lat: pad + (north - lat) / (north - south) * (h - 2 * pad)
    out = [f'<rect class="frame" x="{pad}" y="{pad}" width="{w - 2 * pad}" height="{h - 2 * pad}"/>']
    out.append(f'<text x="{pad + 4}" y="{pad + 12}">{north:.2f}N</text><text x="{pad + 4}" y="{h - pad - 5}">{south:.2f}N</text>')
    out.append(f'<text x="{w - pad - 4}" y="{h - pad - 5}" text-anchor="end">{abs(east):.2f}W</text>')
    out.append(f'<text x="{w - pad - 4}" y="{pad + 12}" text-anchor="end">{abs(west):.2f}W</text>')
    cs, cw, cn, ce = (v for v in AREAS_CITY)
    if bbox != AREAS_CITY:
        out.append(f'<rect class="box" x="{X(cw):.1f}" y="{Y(cn):.1f}" width="{X(ce) - X(cw):.1f}" height="{Y(cs) - Y(cn):.1f}"/>')
    for i, lat, lon, in_city in pts:
        if not (south <= lat <= north and west <= lon <= east):
            continue
        cls = "pt city" if in_city else "pt"
        out.append(f'<circle class="{cls}" cx="{X(lon):.1f}" cy="{Y(lat):.1f}" r="{r}"><title>OpenStreetMap node {esc(i)}</title></circle>')
        if i in new_ids:
            out.append(f'<circle class="new" cx="{X(lon):.1f}" cy="{Y(lat):.1f}" r="{r + 3}"/>')
    return (
        f'<figure class="flock-fig"><figcaption>{esc(caption)}</figcaption>'
        f'<svg class="flock-map" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(caption)}">{"".join(out)}</svg></figure>'
    )


def map_section(hist):
    snaps = hist["snapshots"]
    latest = snaps[-1]
    prev = set(snaps[-2]["county"]) if len(snaps) > 1 else set()
    new_ids = set(latest["county"]) - prev if prev else set()
    city = set(latest["city"])
    pts = [(i, hist["nodes"][i]["lat"], hist["nodes"][i]["lon"], i in city) for i in latest["county"] if i in hist["nodes"]]
    areas = hist.get("areas") or {k: {"bbox": list(v["bbox"])} for k, v in DEFAULT_AREAS.items()}
    county_bb, city_bb = tuple(areas["county"]["bbox"]), tuple(areas["city"]["bbox"])
    global AREAS_CITY
    AREAS_CITY = city_bb
    maps = (
        dot_map(county_bb, pts, new_ids, f"Laramie County box, {latest['date']}", r=3)
        + dot_map(city_bb, pts, new_ids, "Cheyenne area box, zoomed", r=4)
    )
    legend = (
        '<div class="flock-legend"><span><i style="border-top-color:var(--high)"></i>Cheyenne area</span>'
        '<span><i></i>Rest of county</span>'
        + ('<span>Ringed: newly mapped since the previous snapshot</span>' if new_ids else "")
        + "</div>"
    )
    links = (
        '<div class="flock-links"><span>Interactive maps:</span>'
        '<a href="https://flockcamera.app/locations/wyoming/cheyenne" rel="noopener noreferrer">flockcamera.app, Cheyenne</a>'
        '<a href="https://www.openstreetmap.org/#map=12/41.14/-104.80" rel="noopener noreferrer">OpenStreetMap, Cheyenne</a></div>'
    )
    return (
        "<section><h2>Map</h2>"
        f'<div class="viz-row">{maps}</div>{legend}'
        '<p class="flock-note" style="margin-top:12px">Every mapped Flock camera in the latest snapshot, plotted by its OpenStreetMap coordinates. '
        "There is no street basemap, because the site does not load outside map tiles; use the links for one. The dashed box on the county map is the Cheyenne area.</p>"
        f"{links}</section>"
    )


ARTICLES = [
    ("23 Sep 2026", "Alaska Dispatch News", "Prosecutors charge 5 Indianapolis police officers accused of misusing access to Flock license plate reader cameras",
     "https://adn.com/nation-world/2026/09/23/prosecutors-charge-5-indianapolis-police-officers-accused-of-misusing-access-to-flock-license-plate-reader-cameras"),
    ("Aug 2026", "Stateline, via Route Fifty", "Flock Safety tightens safeguards as states, cities question surveillance network",
     "https://www.route-fifty.com/digital-government/2026/08/flock-safety-tightens-safeguards-states-cities-question-surveillance-network/415455/"),
    ("12 Aug 2026", "Cowboy State Daily", "Supporters Say Cheyenne License Plate Readers Work; Opponents Say That\u2019s The Problem",
     "https://cowboystatedaily.com/2026/08/12/supporters-say-wyoming-license-plate-readers-work-opponents-say-thats-the-problem/"),
    ("12 Aug 2026", "Semafor", "Flock tightens guardrails aimed at stopping cops from abusing its license plate cameras",
     "https://semafor.com/article/08/12/2026/flock-adds-guardrails-to-prevent-cops-from-abusing-its-license-plate-cameras"),
    ("2 Aug 2026", "Washington Post, via Alaska Dispatch News", "How rogue officers turned a nationwide camera network into a tool for stalking",
     "https://www.adn.com/nation-world/2026/08/02/how-rogue-officers-turned-a-nationwide-camera-network-into-a-tool-for-stalking/"),
    ("3 Jul 2026", "Cowboy State Daily", "Unlike Other Areas In Wyoming, Glenrock\u2019s Flock Cameras Bring Little Drama",
     "https://cowboystatedaily.com/2026/07/03/unlike-cheyenne-jackson-and-the-reservation-glenrocks-flock-cameras-bring-little-drama/"),
    ("19 Jun 2026", "Cowboy State Daily", "We Know Surveillance Cameras Are Being Used, But So Are Surveillance Microphones",
     "https://cowboystatedaily.com/2026/06/19/we-know-surveillance-cameras-are-being-used-but-so-are-surveillance-microphones/"),
    ("28 Feb 2026", "Cowboy State Daily", "Privacy Advocates Trying To Get Flock License Plate Cams In Cheyenne Removed",
     "https://cowboystatedaily.com/2026/02/28/petition-says-cheyennes-flock-license-plate-cams-invade-privacy/"),
    ("11 Feb 2026", "WHRO Public Media", "A federal judge ruled Norfolk\u2019s Flock surveillance cameras don\u2019t invade people\u2019s privacy, yet",
     "https://whro.org/business-growth/2026-02-11/a-federal-judge-ruled-norfolks-flock-surveillance-cameras-dont-invade-peoples-privacy-yet"),
    ("Dec 2025", "404 Media", "Flock Exposed Its AI-Powered Cameras to the Internet. We Tracked Ourselves",
     "https://www.404media.co/flock-exposed-its-ai-powered-cameras-to-the-internet-we-tracked-ourselves/"),
    ("Nov 2025", "Electronic Frontier Foundation", "How Cops Are Using Flock Safety\u2019s ALPR Network To Surveil Protesters And Activists",
     "https://www.eff.org/deeplinks/2025/11/how-cops-are-using-flock-safetys-alpr-network-surveil-protesters-and-activists"),
]


def capture_section():
    return (
        "<section><h2>What the cameras record</h2>"
        "<p>A Flock license plate camera is a camera. It photographs every vehicle that passes, and the plate read is only the part that gets indexed first. "
        'Flock describes a "vehicle fingerprint" feature that also records the make, body type, color, decals, bumper stickers and roof racks, '
        "and whether a plate is missing or temporary, so a search can run on a description with no plate number "
        '(<a href="https://www.flocksafety.com/blog/vehicle-recognition-software-for-investigation-grade-lpr" rel="noopener noreferrer">Flock\u2019s own description</a>). '
        "What else shows in an image depends on the camera\u2019s angle and lighting.</p>"
        '<p style="margin-top:12px">Some Flock models are general video cameras, not plate readers. 404 Media reported in December 2025 that dozens of Flock\u2019s '
        "Condor pan-tilt-zoom cameras, which can be set to zoom in on people, had live video streams and admin panels reachable from the open internet. "
        "The product line and its capabilities change, so treat this as a description of what has been reported, not a spec sheet.</p></section>"
    )


def data_section():
    a = lambda url, text: f'<a href="{url}" rel="noopener noreferrer">{text}</a>'
    stateline = "https://www.route-fifty.com/digital-government/2026/08/flock-safety-tightens-safeguards-states-cities-question-surveillance-network/415455/"
    flock_view = "https://flocksafety.com/blog/does-flock-enable-mass-surveillance"
    wapo_adn = "https://www.adn.com/nation-world/2026/08/02/how-rogue-officers-turned-a-nationwide-camera-network-into-a-tool-for-stalking/"
    adn = "https://adn.com/nation-world/2026/09/23/prosecutors-charge-5-indianapolis-police-officers-accused-of-misusing-access-to-flock-license-plate-reader-cameras"
    eff = "https://www.eff.org/deeplinks/2025/11/how-cops-are-using-flock-safetys-alpr-network-surveil-protesters-and-activists"
    whro = "https://whro.org/business-growth/2026-02-11/a-federal-judge-ruled-norfolks-flock-surveillance-cameras-dont-invade-peoples-privacy-yet"
    lawsuit = "https://www.yahoo.com/news/articles/police-cameras-tracked-one-driver-090000185.html"
    return (
        "<section><h2>Where the data goes</h2>"
        "<p>Each capture, meaning the plate read, the vehicle attributes, an image, the time and the camera\u2019s location, is uploaded to Flock\u2019s cloud "
        "and searched through Flock\u2019s software. The public cannot search it. Access belongs to the agency or business that owns the camera and to whoever "
        "that owner shares with. Flock describes sharing one-to-one between departments, within a radius or across a state, plus a national lookup for one full plate number "
        f"({a(stateline, 'Stateline, Aug 2026')}). Each owner sets its own sharing and retention. "
        "Flock now recommends seven days of retention, down from a 30-day default, and the change does not automatically apply to existing customers.</p>"

        '<p style="margin-top:12px">Every read carries a time and a place, so the reads for one plate form a trail. Each camera a vehicle passes adds a point, '
        "and a search on that plate returns where it was and when. The more cameras along someone\u2019s routes, the denser the trail, and shared access carries it past one "
        "department\u2019s cameras. "
        f"One lawsuit alleges {a(lawsuit, 'police cameras tracked one driver 526 times in four months')}; the headline does not say whose cameras. "
        "Privacy groups including the ACLU and EFF argue that a searchable history like this lets someone reconstruct a person\u2019s movements without a warrant. "
        f"Flock {a(flock_view, 'argues')} its cameras cannot track the whole of anyone\u2019s movements.</p>"

        '<p style="margin-top:12px">The courts have not settled it. In January 2026 a federal judge in Virginia held that Norfolk\u2019s Flock system, as it is used there, '
        f"is not a Fourth Amendment search, and that the plaintiffs lacked standing; they are appealing ({a(whro, 'WHRO, Feb 2026')}). "
        "That is one district court on one city\u2019s facts, not a rule for Wyoming.</p>"

        '<p style="margin-top:12px">How the access is used is a separate question from what the cameras can do. '
        f"A Washington Post analysis, {a(wapo_adn, 'reprinted by the Alaska Dispatch News')}, found at least 50 officers charged or accused of misusing license plate readers, "
        "and 26 of them used Flock\u2019s cameras to spy on current or former partners or people they hoped to meet. "
        f"In September 2026 prosecutors {a(adn, 'charged five Indianapolis police officers')} with misusing access to Flock cameras. "
        f"EFF\u2019s analysis of audit logs covering more than 12 million searches by over 3,900 agencies, December 2024 to October 2025, "
        f"{a(eff, 'found more than 50 agencies')} that ran hundreds of searches connected to protest activity, often with only \u201cprotest\u201d typed in the reason field. "
        "Flock\u2019s own post reads the same review as 19 of about 3,900 agencies, so the count depends on what is measured. "
        "Flock calls misuse unacceptable. It says it will require an audit tool and case codes on searches by the end of the year.</p>"

        '<p style="margin-top:12px">Cheyenne\u2019s own retention and sharing settings were not in the coverage reviewed for this page. '
        "The city council\u2019s records, or a public records request to the police department, would settle it.</p></section>"
    )


def coverage_section():
    items = "".join(
        f'<li><span class="when">{esc(when)}</span><span><a href="{esc(url)}" rel="noopener noreferrer">{title}</a>'
        f'<br><span class="who">{esc(who)}</span></span></li>'
        for when, who, title, url in ARTICLES
    )
    return (
        "<section><h2>Recent coverage</h2>"
        '<p class="flock-note" style="margin-bottom:14px">Local and national reporting, newest first. Links go to the publishers; this page does not endorse any article\u2019s conclusions.</p>'
        f'<ul class="flock-list">{items}</ul></section>'
    )


def kpis(rows):
    last = rows[-1]
    sub_c = f'as of {last["date"]}'
    month = "n/a"
    cutoff = d(last["date"]) - dt.timedelta(days=30)
    base = [r for r in rows if d(r["date"]) <= cutoff]
    if base:
        month = f'{last["county"] - base[-1]["county"]:+d}'
    return kpi_row([
        ("Flock cameras mapped, Laramie County", str(last["county"]), sub_c),
        ("Of those, Cheyenne area", str(last["city"]), sub_c),
        ("Change in county, last 30 days", month, "n/a until 30 days of history" if month == "n/a" else f'vs {base[-1]["date"]}'),
        ("ALPR of any make, county box", str(rows[-1].get("alpr_total", "n/a")), "includes cameras with no maker tag"),
    ])


def build(hist):
    rows = series(hist)
    title = "Flock Camera Tracker, Cheyenne and Laramie County | Infinity Shield"
    desc = "Flock Safety license plate reader cameras mapped in Cheyenne and Laramie County, Wyoming, from OpenStreetMap, tracked over time."
    parts = [head(title, desc).replace("</head>", STYLE + "\n</head>", 1), nav(None), '<div class="wrap">', "  <header>"]
    updated = hist.get("updated") or (rows[-1]["date"] if rows else "no data yet")
    parts.append(
        '    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>Cheyenne and Laramie County, WY</span>'
        f'<span>Updated {esc(updated)}</span><span>Source: OpenStreetMap</span></div>'
    )
    parts.append("    <h1>Flock Camera <span>Tracker</span></h1>")
    parts.append(
        '    <p class="lede">Flock Safety license plate reader cameras mapped in Cheyenne and the rest of Laramie County, '
        "counted from OpenStreetMap and tracked over time.</p>"
    )
    parts.append("  </header>")

    if not rows:
        parts.append('<div class="flock-empty">No data yet. The first snapshot is collected automatically and the charts appear here once it is in.</div>')
    else:
        parts += [kpis(rows), '<section><h2>Over time</h2>', line_chart(rows)]
        if len(rows) < 2:
            parts.append('<p class="flock-note" style="margin-top:14px">One snapshot so far. The trend lines appear once there are two.</p>')
        extra = add_chart(rows)
        if extra:
            parts.append(extra)
        parts += [table_snapshots(rows), "</section>"]
        parts.append(map_section(hist))
        recent = table_recent(hist, rows)
        if recent:
            parts.append(recent)

    parts += [capture_section(), data_section(), coverage_section()]
    areas = hist.get("areas") or {k: {"label": v["label"], "bbox": list(v["bbox"])} for k, v in DEFAULT_AREAS.items()}
    bb = "; ".join(f'{v["label"]}: {", ".join(str(x) for x in v["bbox"])}' for v in areas.values())
    parts += [
        "<section><h2>How to read this</h2>",
        '<p class="flock-note">These are cameras volunteers have mapped, not an official inventory. A jump in the line usually means someone surveyed '
        "an area, so it tracks installation but does not measure it, and cameras that were never mapped are missing. "
        "Counts include only nodes tagged as Flock Safety by manufacturer or brand; the fourth tile counts every plate reader tagged in the box, whatever the maker.</p>",
        '<p class="flock-note" style="margin-top:12px">Both areas are rectangles (south, west, north, east), not legal boundaries, so the county box takes in a '
        f"sliver of neighbouring counties on its north and west edges. {esc(bb)}. Earlier snapshots marked <span class=\"mono\">attic</span> are rebuilt from "
        "OpenStreetMap edit history, so they show what was mapped by that date and nothing about the days before it was surveyed.</p></section>",
        '  <footer>Map data © <a href="https://www.openstreetmap.org/copyright" rel="noopener noreferrer">OpenStreetMap contributors</a>, '
        'available under the <a href="https://opendatacommons.org/licenses/odbl/" rel="noopener noreferrer">Open Database Licence</a>. '
        'Collected through the Overpass API. · <a href="/">Home</a> · <a href="/brief/">Current Brief</a></footer>',
        "</div>", "", "</body>", "</html>",
    ]
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    hist = json.loads(Path(a.data).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(hist), encoding="utf-8")
    print(f"built {out}")


if __name__ == "__main__":
    main()
