#!/usr/bin/env python3
"""
Fetch a vector basemap for the Flock tracker map from OpenStreetMap (Overpass)
and save it to flock/data/wy-basemap.json: Wyoming county lines, interstates,
trunk and primary highways, named places, and street detail around Cheyenne.

The site loads no outside map tiles, so this is stored as plain geometry and
drawn by the page itself. Each piece is fetched on its own and merged into the
existing file, so one failed Overpass call keeps everything already collected.

Usage (from the repo root):
  python3 tools/collect_basemap.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_flock as cf  # noqa: E402

OUT = cf.ROOT / "flock" / "data" / "wy-basemap.json"
STATE = cf.AREAS["state"]["bbox"]
CITY = cf.AREAS["city"]["bbox"]
EPS_STATE = 0.002   # simplification tolerance in degrees (about 220 m) for state-wide lines
EPS_DETAIL = 0.0004  # about 40 m, for the Cheyenne street detail


def box(bb):
    return "(" + ",".join(str(v) for v in bb) + ")"


def _perp(pt, a, b):
    (y, x), (y1, x1), (y2, x2) = pt, a, b
    if (x1, y1) == (x2, y2):
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    return abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / (((y2 - y1) ** 2 + (x2 - x1) ** 2) ** 0.5)


def simplify(pts, eps):
    """Ramer-Douglas-Peucker on (lat, lon) pairs, iterative so long ways cannot overflow the stack."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        dmax, k = 0.0, None
        for m in range(i + 1, j):
            dist = _perp(pts[m], pts[i], pts[j])
            if dist > dmax:
                dmax, k = dist, m
        if k is not None and dmax > eps:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, kp in zip(pts, keep) if kp]


def geom(points, eps):
    return simplify([(round(p["lat"], 4), round(p["lon"], 4)) for p in points or [] if "lat" in p and "lon" in p], eps)


def parse_places(data):
    out = []
    for el in data.get("elements", []):
        if el.get("type") == "node" and "lat" in el and el.get("tags", {}).get("name"):
            t = el["tags"]
            try:
                pop = int(str(t.get("population", "0")).replace(",", ""))
            except ValueError:
                pop = 0
            out.append({"name": t["name"], "type": t.get("place"), "lat": round(el["lat"], 4), "lon": round(el["lon"], 4), "pop": pop})
    return out


def parse_roads(data, eps):
    out = []
    for el in data.get("elements", []):
        if el.get("type") == "way":
            t = el.get("tags", {})
            pts = geom(el.get("geometry"), eps)
            if len(pts) > 1:
                out.append({"cls": t.get("highway", ""), "ref": t.get("ref") or t.get("name") or "", "pts": pts})
    return out


def parse_counties(data, eps):
    """County boundary segments for counties whose centre lies inside Wyoming (the query also returns neighbours)."""
    s, w, n, e = STATE
    segs = []
    for el in data.get("elements", []):
        if el.get("type") != "relation":
            continue
        rings = [geom(m.get("geometry"), eps) for m in el.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "inner")]
        rings = [r for r in rings if len(r) > 1]
        allp = [p for r in rings for p in r]
        if not allp:
            continue
        clat = (min(p[0] for p in allp) + max(p[0] for p in allp)) / 2
        clon = (min(p[1] for p in allp) + max(p[1] for p in allp)) / 2
        if s <= clat <= n and w <= clon <= e:
            segs += rings
    return segs


PIECES = [
    ("places", lambda: f'[out:json][timeout:120];node["place"~"^(city|town|village|hamlet|suburb)$"]["name"]{box(STATE)};out body;',
     lambda d: parse_places(d), "places"),
    ("interstates and trunk roads", lambda: f'[out:json][timeout:180];way["highway"~"^(motorway|trunk)$"]{box(STATE)};out geom;',
     lambda d: parse_roads(d, EPS_STATE), "roads_major"),
    ("primary roads", lambda: f'[out:json][timeout:180];way["highway"="primary"]{box(STATE)};out geom;',
     lambda d: parse_roads(d, EPS_STATE), "roads_primary"),
    ("county lines", lambda: f'[out:json][timeout:180];relation["boundary"="administrative"]["admin_level"="6"]["name"~"County$"]{box(STATE)};out geom;',
     lambda d: parse_counties(d, 0.003), "boundary"),
    ("Cheyenne streets", lambda: f'[out:json][timeout:120];way["highway"~"^(secondary|tertiary|unclassified)$"]{box(CITY)};out geom;',
     lambda d: parse_roads(d, EPS_DETAIL), "roads_detail"),
]


def main():
    base = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    got = []
    for label, make, parse, key in PIECES:
        try:
            data = cf.call_overpass(make())
            items = parse(data)
        except RuntimeError as exc:
            print(f"{label}: FAILED, {exc}", file=sys.stderr, flush=True)
            continue
        if not items:
            print(f"{label}: empty reply, keeping what the file already has", file=sys.stderr, flush=True)
            continue
        base[key] = items
        got.append(key)
        print(f"{label}: {len(items)} items", flush=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        base["fetched"] = dt.date.today().isoformat()
        OUT.write_text(json.dumps(base, separators=(",", ":")) + "\n", encoding="utf-8")  # keep progress after each piece
        import time
        time.sleep(cf.PAUSE)
    if not got:
        sys.exit("no basemap piece succeeded; nothing written")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB), updated: {', '.join(got)}")


if __name__ == "__main__":
    main()
