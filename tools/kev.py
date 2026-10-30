#!/usr/bin/env python3
"""
CISA Known Exploited Vulnerabilities (KEV) data for the rolling brief.

refresh() downloads the public KEV feed and writes a trimmed snapshot to
brief/data/kev.json (entries added in the last 180 days plus catalog metadata).
If the download fails, the existing snapshot is kept, so a network block never
breaks a build; the page then shows the snapshot's date.

load() returns the snapshot or None. summarize() computes what the page shows.
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "brief" / "data" / "kev.json"
FEED = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
KEEP_DAYS = 180
FIELDS = ("cveID", "vendorProject", "product", "vulnerabilityName", "dateAdded", "dueDate", "knownRansomwareCampaignUse")


def refresh(timeout=25):
    try:
        req = urllib.request.Request(FEED, headers={"User-Agent": "infinityshield-brief-build/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            feed = json.load(r)
    except Exception as e:  # network policy, timeout, bad JSON: keep the old snapshot
        print(f"kev: feed not refreshed ({e.__class__.__name__}: {e}); using snapshot if present", file=sys.stderr)
        return False
    cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    entries = [{k: v.get(k) for k in FIELDS} for v in feed.get("vulnerabilities", []) if v.get("dateAdded", "") >= cutoff]
    snap = {
        "catalogVersion": feed.get("catalogVersion"),
        "dateReleased": feed.get("dateReleased"),
        "totalCount": feed.get("count"),
        "fetched": dt.date.today().isoformat(),
        "keepDays": KEEP_DAYS,
        "entries": sorted(entries, key=lambda e: (e["dateAdded"], e["cveID"])),
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"kev: snapshot written, {len(entries)} entries from the last {KEEP_DAYS} days")
    return True


def load():
    if not SNAPSHOT.exists():
        return None
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _d(s):
    return dt.date.fromisoformat(s)


def summarize(snap, window_start, window_end, brief_text, today=None, weeks=12, due_within=14):
    """window_* are dates; brief_text is the brief JSON dumped to a string (for CVE matching)."""
    today = today or dt.date.today()
    entries = snap["entries"]
    in_window = [e for e in entries if window_start <= _d(e["dateAdded"]) <= window_end]
    due_soon = [e for e in entries if today <= _d(e["dueDate"]) <= today + dt.timedelta(days=due_within)]
    due_soon.sort(key=lambda e: (e["dueDate"], e["vendorProject"]))
    brief_cves = set(re.findall(r"CVE-\d{4}-\d{4,7}", brief_text))
    kev_cves = {e["cveID"] for e in entries}
    in_brief_and_kev = sorted(brief_cves & kev_cves)
    # weekly buckets ending on window_end, newest last
    buckets = []
    end = window_end
    for _ in range(weeks):
        start = end - dt.timedelta(days=6)
        n = sum(1 for e in entries if start <= _d(e["dateAdded"]) <= end)
        buckets.append({"start": start, "end": end, "count": n})
        end = start - dt.timedelta(days=1)
    buckets.reverse()
    return {
        "in_window": in_window,
        "in_window_count": len(in_window),
        "ransomware_in_window": sum(1 for e in in_window if str(e.get("knownRansomwareCampaignUse", "")).lower() == "known"),
        "due_soon": due_soon,
        "in_brief_and_kev": in_brief_and_kev,
        "weekly": buckets,
        "snapshot_date": snap.get("fetched"),
        "catalog_version": snap.get("catalogVersion"),
        "total_count": snap.get("totalCount"),
    }


if __name__ == "__main__":
    ok = refresh()
    sys.exit(0 if ok or SNAPSHOT.exists() else 1)
