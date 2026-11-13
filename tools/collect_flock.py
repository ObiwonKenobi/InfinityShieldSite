#!/usr/bin/env python3
"""
Collect Flock Safety camera counts for Wyoming, Laramie County and Cheyenne,
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
  python3 tools/collect_flock.py --backfill 2023-01 --budget-minutes 40
                                                    stop starting new queries after 40 minutes

The file is saved after every snapshot, newest first, and months already in the file are
skipped, so an interrupted or timed-out run keeps what it got and a rerun continues from there.

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
    "state": {"label": "Wyoming", "bbox": (41.0, -111.0568, 45.0, -104.0522)},  # Wyoming is a rectangle by statute
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
    s, w, n, e = AREAS["state"]["bbox"]
    stamp = f'[date:"{date}T00:00:00Z"]' if date else ""
    return (
        f"[out:json][timeout:180]{stamp};"
        f'node["man_made"="surveillance"]["surveillance:type"="ALPR"]({s},{w},{n},{e});'
        "out body;"
    )


def call_overpass(query):
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for url in ENDPOINTS:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
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
    """Return (alpr_state, alpr_county, {node_id: {lat, lon}}): ALPR of any make in Wyoming, ALPR of any make
    in the county box, and the Flock nodes in Wyoming, at date (None = now)."""
    data = call_overpass(build_query(date))
    if "elements" not in data:
        raise RuntimeError("Overpass reply has no 'elements' key")
    # An overloaded server can answer 200 with an empty list and a remark such as
    # "runtime error: Query timed out". That is a failure, not a count of zero.
    if data.get("remark") and "error" in data["remark"].lower():
        raise RuntimeError(f"Overpass reported: {data['remark']}")
    alpr_state = alpr_county = 0
    flock = {}
    for el in data["elements"]:
        if el.get("type") != "node":
            continue
        if "lat" not in el or "lon" not in el:
            raise RuntimeError(f"node {el.get('id')} came back without coordinates; the query must use 'out body'")
        alpr_state += 1
        if inside(AREAS["county"]["bbox"], el["lat"], el["lon"]):
            alpr_county += 1
        if is_flock(el.get("tags", {})):
            flock[str(el["id"])] = {"lat": round(el["lat"], 5), "lon": round(el["lon"], 5)}
    return alpr_state, alpr_county, flock


def load():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return {"schema": 1, "snapshots": [], "nodes": {}}


def add_snapshot(hist, date, alpr_state, alpr_county, flock, source):
    ids_state = sorted(flock, key=int)
    ids_county = [i for i in ids_state if inside(AREAS["county"]["bbox"], flock[i]["lat"], flock[i]["lon"])]
    ids_city = [i for i in ids_county if inside(AREAS["city"]["bbox"], flock[i]["lat"], flock[i]["lon"])]
    hist["snapshots"] = [s for s in hist["snapshots"] if s["date"] != date]
    hist["snapshots"].append({
        "date": date,
        "source": source,
        "alpr_total": alpr_county,   # ALPR of any make in the county box
        "alpr_state": alpr_state,    # ALPR of any make in Wyoming
        "state": ids_state,
        "county": ids_county,
        "city": ids_city,
    })
    hist["snapshots"].sort(key=lambda s: s["date"])
    for i, pos in flock.items():
        hist["nodes"].setdefault(i, pos)
    return len(ids_state), len(ids_county), len(ids_city)


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
    ap.add_argument("--budget-minutes", type=float, default=0, help="stop starting new queries after this long (0 = no limit)")
    ap.add_argument("--allow-zero", action="store_true", help="accept a live count of zero ALPR (normally treated as a bad reply)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    hist = load()
    today = dt.date.today()
    have = {s["date"] for s in hist["snapshots"] if "state" in s}  # older county-only snapshots are redone
    jobs = [(today.isoformat(), "overpass-live")]  # the live count always comes first
    if args.backfill:
        y, m = (int(x) for x in args.backfill.split("-"))
        older = [d.isoformat() for d in months((y, m), today) if d < today.replace(day=1)]
        jobs += [(d, "overpass-attic") for d in reversed(older) if d not in have]  # newest first, resume-safe

    t0 = time.monotonic()
    done = skipped = 0
    for n, (date, source) in enumerate(jobs):
        if args.budget_minutes and (time.monotonic() - t0) / 60 > args.budget_minutes:
            skipped = len(jobs) - n
            print(f"time budget of {args.budget_minutes:g} min used; {skipped} snapshot(s) left for the next run", flush=True)
            break
        if n:
            time.sleep(PAUSE)
        stamp = None if source == "overpass-live" else date
        try:
            alpr_state, alpr_total, flock = snapshot(stamp)
        except RuntimeError as exc:
            print(f"{date}: FAILED, {exc}", file=sys.stderr, flush=True)
            continue
        if alpr_total == 0 and source == "overpass-live" and not args.allow_zero:
            print(f"{date}: FAILED, 0 ALPR nodes in the county box today. Cameras are known to be mapped here, "
                  "so this is treated as a bad query or reply; use --allow-zero if it is real", file=sys.stderr, flush=True)
            continue
        earlier = [s for s in hist["snapshots"] if s["date"] < date]
        if alpr_total == 0 and earlier and earlier[-1].get("alpr_total"):
            print(f"{date}: FAILED, 0 ALPR returned but the previous snapshot had {earlier[-1]['alpr_total']}; "
                  "treating it as a bad reply, not a drop to zero", file=sys.stderr, flush=True)
            continue
        st, c, k = add_snapshot(hist, date, alpr_state, alpr_total, flock, source)
        print(f"{date}: {st} Flock in Wyoming, {c} in county box, {k} in Cheyenne box, {alpr_state} ALPR of any make statewide ({source})", flush=True)
        done += 1
        if not args.dry_run:
            save(hist)  # keep progress even if a later query hangs

    if not done:
        sys.exit("no snapshot succeeded; nothing written")
    if args.dry_run:
        print("dry run: nothing written")
        return
    print(f"wrote {HISTORY} ({done} new snapshot(s))", flush=True)


if __name__ == "__main__":
    main()
