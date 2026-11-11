#!/usr/bin/env python3
"""
Collect Flock Safety camera counts for Cheyenne and Laramie County, Wyoming,
from OpenStreetMap through the Overpass API, and append them to
flock/data/history.json.

The data is crowd-mapped. A rise in the count means volunteers mapped more
cameras, which tracks installation but is not the same thing. Both areas are
bounding boxes, not legal boundaries; see AREAS below.

Usage (from the repo root):
  python3 tools/collect_flock.py                    snapshot of the current OSM data, dated today
  python3 tools/collect_flock.py --backfill 2023-01 monthly snapshots from that month to today,
                                                    built from OSM edit history (Overpass "attic")
  python3 tools/collect_flock.py --dry-run          print the counts, write nothing

A snapshot for a date that is already in the file is replaced, so reruns are safe.
If the Overpass call fails, nothing is written.
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "flock" / "data" / "history.json"

# (south, west, north, east). Rectangles over the real areas: Laramie County
# is not a rectangle, so the county box takes in a sliver of neighbouring
# counties on its north and west edges.
AREAS = {
    "county": {"label": "Laramie County (bounding box)", "bbox": (40.99, -105.28, 41.60, -104.05)},
    "city": {"label": "Cheyenne area (bounding box)", "bbox": (41.07, -104.95, 41.24, -104.65)},
}

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "infinityshield-flock-tracker/1.0"
PAUSE = 6  # seconds between calls, to stay inside Overpass fair use


def build_query(date):
    s, w, n, e = AREAS["county"]["bbox"]
    stamp = f'[date:"{date}T00:00:00Z"]' if date else ""
    return (
        f"[out:json][timeout:120]{stamp};"
        f'node["man_made"="surveillance"]["surveillance:type"="ALPR"]({s},{w},{n},{e});'
        "out tags;"
    )


def call_overpass(query):
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for url in ENDPOINTS:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = f"{url}: {exc}"
            print(f"  endpoint failed, trying next: {last}", file=sys.stderr)
    raise RuntimeError(f"all Overpass endpoints failed, last error: {last}")


def inside(bbox, lat, lon):
    s, w, n, e = bbox
    return s <= lat <= n and w <= lon <= e


def is_flock(tags):
    text = " ".join(tags.get(k, "") for k in ("manufacturer", "brand", "name", "operator:type")).lower()
    return "flock" in text


def snapshot(date):
    """Return (alpr_total, {node_id: {lat, lon}}) for Flock nodes in the county box at date (None = now)."""
    data = call_overpass(build_query(date))
    if "elements" not in data:
        raise RuntimeError("Overpass reply has no 'elements' key")
    alpr_total = 0
    flock = {}
    for el in data["elements"]:
        if el.get("type") != "node" or "lat" not in el:
            continue
        alpr_total += 1
        if is_flock(el.get("tags", {})):
            flock[str(el["id"])] = {"lat": round(el["lat"], 5), "lon": round(el["lon"], 5)}
    return alpr_total, flock


def load():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return {"schema": 1, "snapshots": [], "nodes": {}}


def add_snapshot(hist, date, alpr_total, flock, source):
    ids_county = sorted(flock, key=int)
    ids_city = [i for i in ids_county if inside(AREAS["city"]["bbox"], flock[i]["lat"], flock[i]["lon"])]
    hist["snapshots"] = [s for s in hist["snapshots"] if s["date"] != date]
    hist["snapshots"].append({
        "date": date,
        "source": source,
        "alpr_total": alpr_total,
        "county": ids_county,
        "city": ids_city,
    })
    hist["snapshots"].sort(key=lambda s: s["date"])
    for i, pos in flock.items():
        hist["nodes"].setdefault(i, pos)
    return len(ids_county), len(ids_city)


def months(start, end):
    y, m = start
    while (y, m) <= (end.year, end.month):
        yield dt.date(y, m, 1)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def save(hist):
    hist["areas"] = {k: {"label": v["label"], "bbox": list(v["bbox"])} for k, v in AREAS.items()}
    hist["updated"] = dt.date.today().isoformat()
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(hist, indent=1) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill", metavar="YYYY-MM", help="also add monthly snapshots from this month")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    hist = load()
    today = dt.date.today()
    jobs = []
    if args.backfill:
        y, m = (int(x) for x in args.backfill.split("-"))
        jobs += [(d.isoformat(), "overpass-attic") for d in months((y, m), today) if d < today.replace(day=1)]
    jobs.append((today.isoformat(), "overpass-live"))

    done = 0
    for n, (date, source) in enumerate(jobs):
        if n:
            time.sleep(PAUSE)
        stamp = None if source == "overpass-live" else date
        try:
            alpr_total, flock = snapshot(stamp)
        except RuntimeError as exc:
            print(f"{date}: FAILED, {exc}", file=sys.stderr)
            continue
        c, k = add_snapshot(hist, date, alpr_total, flock, source)
        print(f"{date}: {c} Flock in county box, {k} in Cheyenne box, {alpr_total} ALPR of any make ({source})")
        done += 1

    if not done:
        sys.exit("no snapshot succeeded; nothing written")
    if args.dry_run:
        print("dry run: nothing written")
        return
    save(hist)
    print(f"wrote {HISTORY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
