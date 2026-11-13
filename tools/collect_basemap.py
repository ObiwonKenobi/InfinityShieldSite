#!/usr/bin/env python3
"""
Fetch a simple basemap for the Flock tracker maps from OpenStreetMap (Overpass)
and save it to flock/data/basemap.json: the Laramie County boundary, interstates
and trunk highways, and named places. tools/build_flock.py draws it under the
camera points when the file exists, and draws nothing when it does not.

The site loads no outside map tiles, so this is stored as plain geometry and
drawn as SVG at build time. Run it once; the geometry barely changes.

Usage (from the repo root):
  python3 tools/collect_basemap.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_flock as cf  # noqa: E402

OUT = cf.ROOT / "flock" / "data" / "basemap.json"
MARGIN = 0.02  # degrees beyond the county box, so edge features are not cut off
EPS = 0.0004   # simplification tolerance in degrees (about 40 m)


def query():
    s, w, n, e = cf.AREAS["county"]["bbox"]
    box = f"({s - MARGIN},{w - MARGIN},{n + MARGIN},{e + MARGIN})"
    return (
        "[out:json][timeout:120];("
        f'node["place"~"^(city|town|village|hamlet|suburb)$"]["name"]{box};'
        f'way["highway"~"^(motorway|trunk)$"]{box};'
        f'relation["boundary"="administrative"]["admin_level"="6"]["name"="Laramie County"]{box};'
        ");out geom;"
    )


def _perp(pt, a, b):
    (y, x), (y1, x1), (y2, x2) = pt, a, b
    if (x1, y1) == (x2, y2):
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    num = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    return num / (((y2 - y1) ** 2 + (x2 - x1) ** 2) ** 0.5)


def simplify(pts, eps=EPS):
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


def geom(points):
    return simplify([(round(p["lat"], 4), round(p["lon"], 4)) for p in points or [] if "lat" in p and "lon" in p])


def parse(data):
    places, roads, boundary = [], [], []
    for el in data.get("elements", []):
        t = el.get("type")
        if t == "node" and "lat" in el:
            tags = el.get("tags", {})
            places.append({"name": tags.get("name"), "type": tags.get("place"), "lat": round(el["lat"], 4), "lon": round(el["lon"], 4)})
        elif t == "way":
            tags = el.get("tags", {})
            pts = geom(el.get("geometry"))
            if len(pts) > 1:
                roads.append({"ref": tags.get("ref") or tags.get("name") or "", "pts": pts})
        elif t == "relation":
            for m in el.get("members", []):
                if m.get("type") == "way" and m.get("role") in ("outer", "inner"):
                    pts = geom(m.get("geometry"))
                    if len(pts) > 1:
                        boundary.append(pts)
    return {"fetched": dt.date.today().isoformat(), "places": places, "roads": roads, "boundary": boundary}


def main():
    data = cf.call_overpass(query())
    base = parse(data)
    print(f"{len(base['places'])} places, {len(base['roads'])} road segments, {len(base['boundary'])} boundary segments", flush=True)
    if not base["places"] or not base["boundary"]:
        sys.exit("basemap reply is missing places or the county boundary; nothing written")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(base, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
