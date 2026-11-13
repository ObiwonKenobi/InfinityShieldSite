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
from charts import kpi_row, ranked_bars  # noqa: E402
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
.flock-svg .ln-state { fill: none; stroke: var(--med); stroke-width: 2.5; }
.flock-svg .dot-state { fill: var(--med); }
.flock-title { display: flex; align-items: center; gap: 18px; }
.flock-title img { height: 56px; width: auto; border: 1px solid var(--border); flex: none; }
.wymap { position: relative; border: 1px solid var(--border); background: var(--bg1); }
.wymap-bar { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.wymap-bar button { font: inherit; font-size: .78rem; color: var(--muted); background: transparent; border: 1px solid var(--border); padding: 4px 10px; cursor: pointer; border-radius: 2px; }
.wymap-bar button:hover, .wymap-bar button:focus-visible { color: var(--text); border-color: var(--accent); outline: none; }
.wymap-count { margin-left: auto; font-family: var(--mono); font-size: .74rem; color: var(--text); }
.wymap-svg { display: block; width: 100%; height: min(70vh, 620px); touch-action: none; cursor: grab; background: var(--bg1); }
.wymap-svg:active { cursor: grabbing; }
.wymap-svg:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.wymap-status { padding: 10px; font-size: .82rem; color: var(--muted); }
.wymap-note { padding: 8px 10px; border-top: 1px solid var(--border); font-size: .72rem; color: var(--faint); }
.wymap .wm-state { fill: #0d1a2a; stroke: #3d5a72; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
.wymap .wm-county { fill: none; stroke: #27415a; stroke-width: 1; vector-effect: non-scaling-stroke; }
.wymap .wm-major { fill: none; stroke: #4b6b86; stroke-width: 1.8; vector-effect: non-scaling-stroke; }
.wymap .wm-primary { fill: none; stroke: #355269; stroke-width: 1.2; vector-effect: non-scaling-stroke; }
.wymap .wm-detail { fill: none; stroke: #2c4459; stroke-width: 1; vector-effect: non-scaling-stroke; }
.wymap .wm-pdot { fill: var(--muted); }
.wymap .wm-ptext { fill: var(--muted); font-size: calc(11px * var(--u, 1)); paint-order: stroke; stroke: #0d1a2a; stroke-width: calc(3px * var(--u, 1)); pointer-events: none; font-family: var(--sans, system-ui, sans-serif); }
.wymap .wm-ptext.big { fill: var(--text); font-size: calc(13px * var(--u, 1)); }
.wymap .wm-cam { fill: var(--accent); fill-opacity: .9; stroke: #060b10; stroke-width: .8; vector-effect: non-scaling-stroke; cursor: pointer; }
.wymap .wm-cam.city { fill: var(--high); }
.wymap .wm-cam:hover { fill: #fff; }
.wymap .wm-new { fill: none; stroke: var(--text); stroke-width: 1.4; vector-effect: non-scaling-stroke; pointer-events: none; }
.flock-svg .hit { outline: none; }
.flock-svg .hitbox { fill: transparent; }
.flock-svg .guide { opacity: 0; stroke: var(--faint); stroke-width: 1; stroke-dasharray: 3 3; }
.flock-svg .tip { opacity: 0; pointer-events: none; }
.flock-svg .hit:hover .tip, .flock-svg .hit:focus .tip { opacity: 1; }
.flock-svg .hit:hover .guide, .flock-svg .hit:focus .guide { opacity: 1; }
.flock-svg .hit:hover .add, .flock-svg .hit:focus .add { fill: #7fc0ea; }
.flock-svg .hit:hover circle, .flock-svg .hit:focus circle { r: 5; }
.flock-svg .tip rect { fill: var(--bg2); stroke: var(--faint); stroke-width: 1; }
.flock-svg .tip text { fill: var(--text); font-size: 12px; }
.flock-svg .tip text.sub { fill: var(--muted); font-size: 11px; }
.flock-svg text.val { fill: var(--text); font-size: 11px; text-anchor: middle; }
.flock-map .bm-bound { fill: none; stroke: #3d5a72; stroke-width: 1.2; stroke-dasharray: 2 3; }
.flock-map .bm-road { fill: none; stroke: #2a4256; stroke-width: 1.6; }
.flock-map .bm-dot { fill: var(--muted); }
.flock-map text.bm-place { fill: var(--muted); font-size: 10.5px; paint-order: stroke; stroke: var(--bg1); stroke-width: 3px; }
.flock-map text.bm-place.big { font-size: 12px; fill: var(--text); }
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
    """Per snapshot: date, state, county and city counts, new ids since the previous snapshot."""
    snaps = hist["snapshots"]
    use_state = bool(snaps) and all("state" in x for x in snaps)  # the added/removed series needs one basis throughout
    out, prev = [], set()
    for x in snaps:
        cur = set(x["state"] if use_state else x["county"])
        out.append({
            "date": x["date"], "state": len(x["state"]) if "state" in x else None,
            "county": len(x["county"]), "city": len(x["city"]),
            "added": len(cur - prev), "removed": len(prev - cur), "source": x.get("source", ""),
            "alpr_total": x.get("alpr_total"), "alpr_state": x.get("alpr_state"),
            "basis": "state" if use_state else "county",
        })
        prev = cur
    return out


def first_seen(hist):
    seen = {}
    for s in hist["snapshots"]:
        for i in s.get("state", s["county"]):
            seen.setdefault(i, s["date"])
    return seen


def nice_max(v):
    """Axis top such that four equal steps are whole numbers (0, 8, 16, 24, 32)."""
    step = max(math.ceil(v / 4), 1)
    if step >= 10:
        unit = 5 if step < 50 else 10
        step = math.ceil(step / unit) * unit
    return 4 * step


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


def tip(cx, lines, top=None):
    """Hover/focus tooltip group. lines[0] is the muted heading, the rest are the numbers."""
    top = PAD_T + 4 if top is None else top
    w = max(len(t) for t in lines) * 6.8 + 20
    h = 12 + 17 * len(lines)
    x = min(max(cx - w / 2, PAD_L), W - PAD_R - w)
    out = [f'<g class="tip"><rect x="{x:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h}" rx="3"/>']
    for i, t in enumerate(lines):
        cls = ' class="sub"' if i == 0 else ""
        out.append(f'<text{cls} x="{x + 10:.1f}" y="{top + 19 + 17 * i:.1f}">{esc(t)}</text>')
    out.append("</g>")
    return "".join(out)


def line_chart(rows):
    dates = [r["date"] for r in rows]
    top = nice_max(max(max(r["county"], r["state"] or 0) for r in rows))
    single = len(rows) == 1
    x = (lambda s_: PAD_L + (W - PAD_L - PAD_R) / 2) if single else x_scale(dates)
    y = y_scale(top)
    has_state = any(r["state"] is not None for r in rows)
    pts = lambda key: " ".join(f"{x(r['date']):.1f},{y(r[key]):.1f}" for r in rows if r[key] is not None)
    lines = ""
    if not single:
        if has_state:
            lines += f'<polyline class="ln-state" points="{pts("state")}"/>'
        lines += f'<polyline class="ln-county" points="{pts("county")}"/><polyline class="ln-city" points="{pts("city")}"/>'
    hitw = 60 if single else max((W - PAD_L - PAD_R) / (len(rows) - 1), 14)
    show_all = len(rows) <= 12
    top_key = "state" if has_state else "county"
    dots, labels, hits = [], [], []
    for k, r in enumerate(rows):
        xi = x(r["date"])
        if r["state"] is not None:
            dots.append(f'<circle class="dot-state" cx="{xi:.1f}" cy="{y(r["state"]):.1f}" r="3"/>')
        if r["county"] != r["state"]:
            dots.append(f'<circle class="dot-county" cx="{xi:.1f}" cy="{y(r["county"]):.1f}" r="3"/>')
        if r["city"] != r["county"]:
            dots.append(f'<circle class="dot-city" cx="{xi:.1f}" cy="{y(r["city"]):.1f}" r="3"/>')
        if r[top_key] is not None and (show_all or k in (0, len(rows) - 1)):
            labels.append(f'<text class="val" x="{xi:.1f}" y="{y(r[top_key]) - 9:.1f}">{r[top_key]}</text>')
        tl = [r["date"]]
        if r["state"] is not None:
            tl.append(f'Wyoming  {r["state"]}')
        tl += [f'Laramie County  {r["county"]}', f'Cheyenne area  {r["city"]}']
        aria = f'{r["date"]}: ' + ", ".join(t.replace("  ", " ") for t in tl[1:])
        hits.append(
            f'<g class="hit" tabindex="0" role="img" aria-label="{esc(aria)}">'
            f'<rect class="hitbox" x="{xi - hitw / 2:.1f}" y="{PAD_T}" width="{hitw:.1f}" height="{H - PAD_T - PAD_B}"/>'
            f'<line class="guide" x1="{xi:.1f}" x2="{xi:.1f}" y1="{PAD_T}" y2="{H - PAD_B}"/>'
            + tip(xi, tl) + "</g>"
        )
    last = rows[-1]
    label = (f"Flock cameras mapped over time. Latest {last['date']}: "
             + (f"{last['state']} in Wyoming, " if last["state"] is not None else "")
             + f"{last['county']} in Laramie County, {last['city']} in Cheyenne.")
    legend = (
        ('<span><i style="border-top-color:var(--med)"></i>' f'Wyoming <b>{last["state"]}</b></span>' if last["state"] is not None else "")
        + f'<span><i></i>Laramie County (box) <b>{last["county"]}</b></span>'
        + f'<span><i class="d"></i>Cheyenne area (box) <b>{last["city"]}</b></span>'
    )
    same = len(rows) > 1 and all(r["county"] == r["city"] for r in rows)
    note = (
        '<p class="flock-note" style="margin-top:10px">The county and Cheyenne lines are identical: every camera mapped in the county box is inside the Cheyenne box, so the dashed line sits under the solid one.</p>'
        if same else ""
    )
    return (
        '<figure class="flock-fig"><figcaption>Cameras mapped, by snapshot date. Hover or tap a point for the numbers.</figcaption>'
        f'<svg class="flock-svg" viewBox="0 0 {W} {H}" role="group" aria-label="{esc(label)}">'
        f'{axes(dates, top, y)}{lines}{"".join(dots)}{"".join(labels)}{"".join(hits)}</svg>'
        f'<div class="flock-legend">{legend}</div>{note}</figure>'
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
        val = f'<text class="val" x="{cx:.1f}" y="{y(r["added"]) - 5:.1f}">{r["added"]}</text>' if n <= 18 else ""
        aria = f'to {r["date"]}: {r["added"]} newly mapped, {r["removed"]} removed'
        bars.append(
            f'<g class="hit" tabindex="0" role="img" aria-label="{esc(aria)}">'
            f'<rect class="hitbox" x="{cx - slot / 2:.1f}" y="{PAD_T}" width="{slot:.1f}" height="{H - PAD_T - PAD_B}"/>'
            f'<rect class="add" x="{cx - bw / 2:.1f}" y="{y(r["added"]):.1f}" width="{bw:.1f}" height="{max(h, 0):.1f}"/>'
            f'{val}' + tip(cx, [f'to {r["date"]}', f'{r["added"]} newly mapped', f'{r["removed"]} removed']) + "</g>"
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
    label = f"Cameras newly mapped between snapshots in {'Wyoming' if rows[-1]['basis'] == 'state' else 'Laramie County'}. " + ", ".join(f'{r["date"]}: {r["added"]}' for r in steps[-6:])
    return (
        f'<figure class="flock-fig"><figcaption>Newly mapped since the previous snapshot ({"Wyoming" if rows[-1]["basis"] == "state" else "county box"}). Hover or tap a bar for the numbers.</figcaption>'
        f'<svg class="flock-svg" viewBox="0 0 {W} {H}" role="group" aria-label="{esc(label)}">{"".join(gridl)}{"".join(bars)}</svg></figure>'
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
    county_ids = set(hist["snapshots"][-1]["county"])
    latest = set(hist["snapshots"][-1].get("state", hist["snapshots"][-1]["county"]))
    new = [(i, dte) for i, dte in seen.items() if dte != first and i in latest]
    new.sort(key=lambda t: (t[1], int(t[0])), reverse=True)
    if not new:
        return ""
    body = "".join(
        f'<tr><td>{esc(dte)}</td><td>{"Cheyenne area" if i in city_ids else ("Rest of Laramie County" if i in county_ids else "Elsewhere in Wyoming")}</td>'
        f'<td><a href="https://www.openstreetmap.org/node/{esc(i)}" rel="noopener noreferrer">node {esc(i)}</a></td></tr>'
        for i, dte in new[:20]
    )
    return (
        '<section><h2>Recently mapped</h2>'
        '<p class="flock-note" style="margin-bottom:14px">Date is the first snapshot a camera appears in, so it is the latest it could have been mapped, not the date it was installed.</p>'
        '<div class="scroll-x"><table class="flock-table"><thead><tr><th>First seen by</th><th>Area</th><th>OpenStreetMap</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div></section>'
    )


def base_layers(base, bbox, X, Y, uid, big_only):
    """Basemap under the points: county boundary, interstates and highways, named places. All optional."""
    south, west, north, east = bbox
    inside = lambda lat, lon: south <= lat <= north and west <= lon <= east
    path = lambda pts: "M" + " L".join(f"{X(lon):.1f},{Y(lat):.1f}" for lat, lon in pts)
    out = [f'<g clip-path="url(#clip-{uid})">']
    for ring in base.get("boundary", []):
        out.append(f'<path class="bm-bound" d="{path(ring)}"/>')
    for road in base.get("roads", []):
        if len(road["pts"]) > 1:
            out.append(f'<path class="bm-road" d="{path(road["pts"])}"/>')
    out.append("</g>")
    rank = {"city": 3, "town": 2, "village": 1, "hamlet": 0, "suburb": 0}
    places = [pl for pl in base.get("places", []) if inside(pl["lat"], pl["lon"]) and pl.get("name")]
    if big_only:
        places = [pl for pl in places if rank.get(pl.get("type"), 0) >= 1]
    placed = []  # label boxes already used, biggest places first so small ones yield
    for pl in sorted(places, key=lambda q: -rank.get(q.get("type"), 0)):
        x, y = X(pl["lon"]), Y(pl["lat"])
        big = " big" if pl.get("type") in ("city", "town") else ""
        anchor, dx = ("end", -5) if x > X(east) - 90 else ("start", 5)
        out.append(f'<circle class="bm-dot" cx="{x:.1f}" cy="{y:.1f}" r="2"/>')
        wlab = len(pl["name"]) * (6.6 if big else 5.9)
        x0 = x + dx if anchor == "start" else x + dx - wlab
        box = (x0 - 2, y - 16, x0 + wlab + 2, y + 2)
        if any(not (box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3]) for o in placed):
            continue
        placed.append(box)
        out.append(f'<text class="bm-place{big}" x="{x + dx:.1f}" y="{y - 4:.1f}" text-anchor="{anchor}">{esc(pl["name"])}</text>')
    return "".join(out)


_map_uid = 0


def dot_map(bbox, pts, new_ids, caption, width=520, r=3, base=None, big_only=False):
    """Static point map: lon/lat scaled by cos(latitude). base is the optional basemap from flock/data/basemap.json. pts: [(id, lat, lon, in_city)]."""
    global _map_uid
    _map_uid += 1
    uid = _map_uid
    south, west, north, east = bbox
    k = math.cos(math.radians((south + north) / 2))
    ww, hh = (east - west) * k, north - south
    pad = 8
    w = width
    h = round(w * hh / ww)
    X = lambda lon: pad + (lon - west) / (east - west) * (w - 2 * pad)
    Y = lambda lat: pad + (north - lat) / (north - south) * (h - 2 * pad)
    out = [f'<clipPath id="clip-{uid}"><rect x="{pad}" y="{pad}" width="{w - 2 * pad}" height="{h - 2 * pad}"/></clipPath>']
    if base:
        out.append(base_layers(base, bbox, X, Y, uid, big_only))
    out.append(f'<rect class="frame" x="{pad}" y="{pad}" width="{w - 2 * pad}" height="{h - 2 * pad}"/>')
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


def legacy_base(wy):
    """Adapt flock/data/wy-basemap.json to the keys the static maps use."""
    if not wy:
        return None
    return {"boundary": wy.get("boundary", []), "roads": wy.get("roads_major", []) + wy.get("roads_primary", []), "places": wy.get("places", [])}


def map_payload(hist):
    """Camera points and view boxes for the zoomable map (written to flock/data/map.json)."""
    snaps = hist["snapshots"]
    latest = snaps[-1]
    ids = latest.get("state", latest["county"])
    prev = set(snaps[-2].get("state", snaps[-2]["county"])) if len(snaps) > 1 else set()
    city = set(latest["city"])
    areas = hist.get("areas") or {k: {"bbox": list(v["bbox"])} for k, v in DEFAULT_AREAS.items()}
    cams = []
    for i in ids:
        pos = hist["nodes"].get(i)
        if pos:
            cams.append([int(i), pos["lat"], pos["lon"], (1 if i in city else 0) | (2 if prev and i not in prev else 0)])
    return {"date": latest["date"], "views": {k: list(areas[k]["bbox"]) for k in ("state", "county", "city") if k in areas}, "cameras": cams}


def map_section(hist, base=None, wy=None):
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
    n_county, n_city = len(latest["county"]), len(latest["city"])
    static = (
        dot_map(county_bb, pts, new_ids, f"Laramie County box, {latest['date']}: {n_county} cameras", r=3, base=base, big_only=True)
        + dot_map(city_bb, pts, new_ids, f"Cheyenne area box, zoomed: {n_city} cameras", r=4, base=base)
    )
    legend = (
        '<div class="flock-legend"><span><i style="border-top-color:var(--high)"></i>Cheyenne area</span>'
        '<span><i></i>Elsewhere</span><span>Ringed: newly mapped since the previous snapshot</span></div>'
    )
    links = (
        '<div class="flock-links"><span>Other maps:</span>'
        '<a href="https://maps.deflock.org/" rel="noopener noreferrer">DeFlock</a>'
        '<a href="https://flockcamera.app/locations/wyoming/cheyenne" rel="noopener noreferrer">flockcamera.app, Cheyenne</a>'
        '<a href="https://www.openstreetmap.org/#map=12/41.14/-104.80" rel="noopener noreferrer">OpenStreetMap, Cheyenne</a></div>'
    )
    has_state = "state" in latest
    bar = (
        '<div class="wymap-bar">'
        '<button type="button" data-view="state">Wyoming</button>'
        '<button type="button" data-view="county">Laramie County</button>'
        '<button type="button" data-view="city">Cheyenne</button>'
        '<button type="button" data-zoom="0.6" aria-label="Zoom in">+</button>'
        '<button type="button" data-zoom="1.6" aria-label="Zoom out">\u2212</button>'
        '<span class="wymap-count" role="status">Loading map</span></div>'
    )
    interactive = (
        '<div class="wymap" id="wymap" data-map="/flock/data/map.json" data-base="/flock/data/wy-basemap.json">'
        f'{bar}<div class="wymap-status"></div>'
        '<svg class="wymap-svg" tabindex="0" role="img" aria-label="Zoomable map of Flock cameras mapped in Wyoming. Drag to pan, scroll or pinch to zoom, arrow keys and plus and minus also work." '
        'viewBox="0 0 512 400"></svg>'
        '<div class="wymap-note">Drag to pan, scroll or pinch to zoom. Click a camera to open it in OpenStreetMap. '
        'Roads, county lines and places are stored on this site from OpenStreetMap; there are no street tiles.</div></div>'
        '<script src="/flock/map.js" defer></script>'
        f'<noscript><p class="flock-note">The zoomable map needs JavaScript. These static maps show the same cameras for the county and for Cheyenne.</p><div class="viz-row">{static}</div></noscript>'
    )
    if not has_state:
        interactive = f'<div class="viz-row">{static}</div>'
    if base:
        note = ("The basemap is drawn from OpenStreetMap geometry: county lines, interstates and highways, and named places. "
                "The site does not load outside map tiles, so there are no street tiles; use the other maps for those.")
    else:
        note = "There is no basemap yet, and the site does not load outside map tiles; use the other maps for one."
    return (
        "<section><h2>Map</h2>"
        f"{interactive}{legend}"
        f'<p class="flock-note" style="margin-top:12px">Every mapped Flock camera in the latest snapshot, plotted by its OpenStreetMap coordinates. {note}</p>'
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
    aclu_case = "https://www.aclu.org/cases/schmidt-v-norfolk"
    mobility = "https://pmc.ncbi.nlm.nih.gov/articles/PMC3607247"
    exposed = "https://www.404media.co/flock-exposed-its-ai-powered-cameras-to-the-internet-we-tracked-ourselves/"
    leaked = "https://www.techlicious.com/blog/former-officers-kept-using-flock-cameras-after-leaving-police/"
    return (
        "<section><h2>Where the data goes</h2>"
        "<p>Each capture, meaning the plate, the vehicle\u2019s attributes, an image, the time and the camera\u2019s location, goes to Flock\u2019s cloud. "
        "Flock\u2019s design limits searching to authorized users: the police or business that owns the camera and whoever they share with. "
        f"Access has not always stayed inside that line, though. Flock cameras have been {a(exposed, 'found streaming to the open internet')}, "
        f"and a {a(leaked, 'report on a Washington Post investigation')} found officers still using their logins after leaving their jobs or while suspended.</p>"
        '<p style="margin-top:12px">Every read carries a time and a place, so searching one plate returns a trail of where that vehicle went and when. '
        "The people running those searches are the police who own the cameras. Critics, including the ACLU and EFF, argue that following people this way without a warrant is unconstitutional. "
        "The federal court in Norfolk that ruled on Flock this year did not decide that for searches of the database.</p>"
        '<p style="margin-top:12px">Cheyenne\u2019s own retention and sharing settings were not in the coverage reviewed for this page. '
        "City council records, or a public records request to the police department, would settle it.</p>"
        '<details class="flock-data" style="margin-top:14px"><summary>The evidence: law, misuse, inference, retention</summary>'

        "<p><b>The law.</b> In January 2026 a federal judge in Virginia held that photographing passing vehicles in Norfolk is not a Fourth Amendment search. "
        "On whether searching the stored database needs a warrant, the court did not reach the question: it found the plaintiffs could not challenge that part because the city had never searched for their vehicles. "
        f"The plaintiffs are appealing, and the ACLU and EFF back them ({a(whro, 'WHRO')}; {a(aclu_case, 'ACLU')}). "
        "It is one district court on one city\u2019s facts, not a rule for Wyoming. State laws differ: "
        f"Flock says it disabled its national lookup in states such as California that bar sharing across state lines ({a(stateline, 'Stateline')}).</p>"

        '<p style="margin-top:10px"><b>Misuse.</b> '
        f"A Washington Post analysis, {a(wapo_adn, 'reprinted by the Alaska Dispatch News')}, found at least 50 officers charged or accused of misusing license plate readers, "
        "and 26 of them used Flock\u2019s cameras to spy on current or former partners or people they hoped to meet. "
        f"In September 2026 prosecutors {a(adn, 'charged five Indianapolis police officers')} with misusing access to Flock cameras. "
        f"EFF\u2019s audit-log analysis, covering more than 12 million searches by over 3,900 agencies, {a(eff, 'found more than 50 agencies')} with searches tied to protest activity, "
        "often with only \u201cprotest\u201d typed as the reason. Flock\u2019s own post reads the same review as 19 of about 3,900 agencies, so the count depends on what is measured. "
        "Flock calls misuse unacceptable and says it will require an audit tool and case codes on searches by year end.</p>"

        '<p style="margin-top:10px"><b>Gaps between cameras.</b> '
        "The road network and the time stamps limit where a vehicle could have been between two reads, and four time-and-place points were enough to identify 95% of 1.5 million mobile phone users "
        f"({a(mobility, 'de Montjoye et al., 2013')}). That study used phone data, not plate readers, and no study of route inference between plate-reader cameras was found. "
        f"Flock {a(flock_view, 'argues')} its cameras cannot track the whole of anyone\u2019s movements. "
        "A plate belongs to a registered owner, and most people commute alone, so a trail usually describes one person, though shared household cars, rentals and fleet vehicles can break that link.</p>"

        '<p style="margin-top:10px"><b>Sharing and retention.</b> '
        "Flock describes sharing one-to-one, within a radius or across a state, plus a national lookup for one full plate number. "
        "It now recommends seven days of retention, down from a 30-day default, and the change does not automatically apply to existing customers.</p>"
        "</details></section>"
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
    sub = f'as of {last["date"]}'
    have_state = last["state"] is not None
    key = "state" if have_state else "county"
    month, since = "n/a", ""
    cutoff = d(last["date"]) - dt.timedelta(days=30)
    base = [r for r in rows if d(r["date"]) <= cutoff and r[key] is not None]
    if base:
        month, since = f'{last[key] - base[-1][key]:+d}', f'vs {base[-1]["date"]}'
    tiles = []
    if have_state:
        tiles.append(("Flock cameras mapped, Wyoming", str(last["state"]), sub))
    tiles += [("Laramie County", str(last["county"]), sub), ("Cheyenne area", str(last["city"]), sub)]
    tiles.append((f'Change in {"Wyoming" if have_state else "county"}, last 30 days', month, since or "n/a until 30 days of history"))
    any_make = last.get("alpr_state") if have_state else last.get("alpr_total")
    tiles.append((f'ALPR of any make, {"Wyoming" if have_state else "county box"}', str(any_make if any_make is not None else "n/a"), "includes cameras with no maker tag"))
    return kpi_row(tiles)


def town_stats(hist, base, top=12):
    """Cameras in the latest snapshot grouped by nearest mapped town. Returns [(name, count)] or None."""
    last = hist["snapshots"][-1]
    if "state" not in last or not base or not base.get("places"):
        return None
    towns = [pl for pl in base["places"] if pl.get("type") in ("city", "town", "village")]
    if not towns:
        return None
    counts = {}
    for i in last["state"]:
        pos = hist["nodes"].get(i)
        if not pos:
            continue
        best, bd = None, 1e9
        for t in towns:
            dx = (pos["lon"] - t["lon"]) * math.cos(math.radians(pos["lat"])) * 111.32
            dy = (pos["lat"] - t["lat"]) * 110.57
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < bd:
                best, bd = t["name"], dist
        key = best if bd <= 30 else "Rural, no town within 30 km"
        counts[key] = counts.get(key, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: -kv[1])
    return rows[:top]


def wyoming_section(hist, base):
    rows = town_stats(hist, base)
    if not rows:
        return ""
    bars = ranked_bars([(n, c, f"{n}: {c} cameras") for n, c in rows], "Cameras by nearest town, latest snapshot",
                       "Each camera is assigned to the nearest city, town or village in OpenStreetMap within 30 km, so a count is the area around a town, not its city limits.")
    return f"<section><h2>Across Wyoming</h2>{bars}</section>"


def build(hist, base=None, wy=None, has_flag=False):
    rows = series(hist)
    wide = bool(rows) and rows[-1]["state"] is not None   # statewide wording only once statewide data exists
    title = ("Flock Camera Tracker, Wyoming" if wide else "Flock Camera Tracker, Cheyenne and Laramie County") + " | Infinity Shield"
    desc = ("Flock Safety license plate reader cameras mapped across Wyoming, with Cheyenne and Laramie County broken out, from OpenStreetMap, tracked over time." if wide
            else "Flock Safety license plate reader cameras mapped in Cheyenne and Laramie County, Wyoming, from OpenStreetMap, tracked over time.")
    page_head = head(title, desc).replace("</head>", STYLE + "\n</head>", 1)
    page_head = page_head.replace("default-src 'none';", "default-src 'none'; script-src 'self'; connect-src 'self';", 1)  # our own map script and data only
    parts = [page_head, nav(None), '<div class="wrap">', "  <header>"]
    updated = hist.get("updated") or (rows[-1]["date"] if rows else "no data yet")
    parts.append(
        f'    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>{"Wyoming, with Laramie County and Cheyenne" if wide else "Cheyenne and Laramie County, WY"}</span>'
        f'<span>Updated {esc(updated)}</span><span>Source: OpenStreetMap</span></div>'
    )
    flag = '<img src="/flock/assets/wyoming-flag.svg" alt="Flag of Wyoming" height="56">' if has_flag else ""
    parts.append(f'    <div class="flock-title">{flag}<h1>Flock Camera <span>Tracker</span></h1></div>')
    parts.append(
        '    <p class="lede">' + ("Flock Safety license plate reader cameras mapped across Wyoming, with Cheyenne and Laramie County broken out, " if wide
        else "Flock Safety license plate reader cameras mapped in Cheyenne and the rest of Laramie County, ")
        + "counted from OpenStreetMap and tracked over time.</p>"
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
        parts.append(map_section(hist, base, wy))
        ws = wyoming_section(hist, wy)
        if ws:
            parts.append(ws)
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
        "Counts include only nodes tagged as Flock Safety by manufacturer or brand; the last tile counts every plate reader tagged in Wyoming, whatever the maker.</p>",
        '<p class="flock-note" style="margin-top:12px">The county and Cheyenne areas are rectangles (south, west, north, east), not legal boundaries, so the county box takes in a '
        f"sliver of neighbouring counties on its north and west edges. The Wyoming box is the state border, which is a rectangle. {esc(bb)}. Earlier snapshots marked <span class=\"mono\">attic</span> are rebuilt from "
        "OpenStreetMap edit history, so they show what was mapped by that date and nothing about the days before it was surveyed.</p></section>",
        '  <footer>Map data © <a href="https://www.openstreetmap.org/copyright" rel="noopener noreferrer">OpenStreetMap contributors</a>, '
        'available under the <a href="https://opendatacommons.org/licenses/odbl/" rel="noopener noreferrer">Open Database Licence</a>. '
        'Collected through the Overpass API.' + (' Flag image: <a href="https://commons.wikimedia.org/wiki/File:Flag_of_Wyoming.svg" rel="noopener noreferrer">Wikimedia Commons</a>.' if has_flag else '') + ' · <a href="/">Home</a> · <a href="/brief/">Current Brief</a></footer>',
        "</div>", "", "</body>", "</html>",
    ]
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    data_path = Path(a.data)
    hist = json.loads(data_path.read_text(encoding="utf-8"))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wy_path = data_path.parent / "wy-basemap.json"
    wy = json.loads(wy_path.read_text(encoding="utf-8")) if wy_path.exists() else None
    base = legacy_base(wy)
    has_flag = (out.parent / "assets" / "wyoming-flag.svg").exists()
    out.write_text(build(hist, base, wy, has_flag), encoding="utf-8")
    if hist["snapshots"]:
        mp = out.parent / "data" / "map.json"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(map_payload(hist), separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"built {out}")


if __name__ == "__main__":
    main()
