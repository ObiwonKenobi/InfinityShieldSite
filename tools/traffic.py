#!/usr/bin/env python3
"""
Visitor count and visit length for the rolling brief, from a self-hosted Umami.

Config is tools/analytics.json. While `host`, `website_id` or `share_id` is empty this does
nothing, the page carries no analytics script, and the security policy is unchanged.

refresh() asks Umami's public share endpoints for the last 30 days of aggregate numbers for
the brief page and writes brief/data/traffic.json. Like the KEV feed, a failed fetch keeps the
previous snapshot so a network block never breaks a build. Only totals are stored: no visitor
records, addresses, or paths other than the brief's own.

Umami counts a visit's length as the time between its first and last event, so a visitor who
loads the page once and leaves is recorded as a zero second visit.
"""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "tools" / "analytics.json"
SNAPSHOT = ROOT / "brief" / "data" / "traffic.json"
DAYS = 30


def config():
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    host = str(c.get("host", "")).strip().rstrip("/")
    if not (host and c.get("website_id") and c.get("share_id")) or not host.startswith("https://"):
        return None
    return {**c, "host": host}


def _get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "infinityshield-brief-build/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _num(v):
    """Umami returns plain numbers in older versions and {"value": n} in newer ones."""
    if isinstance(v, dict):
        v = v.get("value")
    return int(v) if isinstance(v, (int, float)) else 0


def refresh():
    c = config()
    if not c:
        return False
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=DAYS)
    since = None
    try:
        since = dt.datetime.fromisoformat(c["since"]).replace(tzinfo=dt.timezone.utc) if c.get("since") else None
    except ValueError:
        pass
    if since and since > start:  # counting began inside the window: do not claim a full 30 days
        start = since
    try:
        share = _get(f'{c["host"]}/api/share/{urllib.parse.quote(c["share_id"])}')
        token = share.get("token")
        wid = share.get("websiteId") or c["website_id"]
        q = urllib.parse.urlencode({"startAt": int(start.timestamp() * 1000), "endAt": int(end.timestamp() * 1000), "path": c.get("path", "/brief/")})
        stats = _get(f'{c["host"]}/api/websites/{urllib.parse.quote(wid)}/stats?{q}', {"x-umami-share-token": token or "", "x-umami-share-context": "1"})
    except Exception as e:  # network policy, timeout, bad JSON, wrong share id: keep the old snapshot
        print(f"traffic: not refreshed ({e.__class__.__name__}: {e}); using snapshot if present", file=sys.stderr)
        return False
    snap = {
        "fetched": end.date().isoformat(), "days": DAYS, "path": c.get("path", "/brief/"),
        "since": start.date().isoformat() if since and since >= end - dt.timedelta(days=DAYS) else None,
        "visitors": _num(stats.get("visitors")), "visits": _num(stats.get("visits")),
        "pageviews": _num(stats.get("pageviews")), "bounces": _num(stats.get("bounces")),
        "totaltime": _num(stats.get("totaltime")),
    }
    SNAPSHOT.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f'traffic: snapshot written, {snap["visitors"]} visitors, {snap["visits"]} visits in {DAYS} days')
    return True


def load():
    if not SNAPSHOT.exists():
        return None
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except ValueError:
        return None


def avg_visit(snap):
    """Average visit length as m:ss, the way Umami's own dashboard computes it (total time over visits)."""
    if not snap or not snap.get("visits"):
        return None
    secs = round(snap["totaltime"] / snap["visits"])
    return f"{secs // 60}:{secs % 60:02d}"


def line(snap):
    """One plain line for the page, or an empty string when there is nothing to show."""
    if not snap:
        return ""
    v = snap["visitors"]
    t = avg_visit(snap)
    when = dt.date.fromisoformat(snap["fetched"])
    stamp = f'{when.day} {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][when.month - 1]}'
    if snap.get("since"):
        d0 = dt.date.fromisoformat(snap["since"])
        head = f'Since {d0.day} {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d0.month - 1]} (counting began that day)'
    else:
        head = f'Last {snap["days"]} days to {stamp}'
    return f'{head}: {v:,} visitor{"s" if v != 1 else ""}' + (f", average visit {t}" if t and snap["visits"] else "")
