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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import ROOT, esc, head, nav  # noqa: E402
from charts import kpi_row  # noqa: E402
from collect_flock import AREAS as DEFAULT_AREAS  # noqa: E402

DATA = ROOT / "flock" / "data" / "history.json"
OUT = ROOT / "flock" / "index.html"

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
        recent = table_recent(hist, rows)
        if recent:
            parts.append(recent)

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
