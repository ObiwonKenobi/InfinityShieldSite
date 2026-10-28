#!/usr/bin/env python3
"""
Fetches KGS job listings, updates jobs/data.json,
and regenerates jobs/index.html + monthly archive pages.
No external dependencies — stdlib only.
"""
import html
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PORTAL = "https://jobs.dayforcehcm.com/kgs/CANDIDATEPORTAL?locationString=Virtual&distance=15&locationId=-9999999"
API_CANDIDATES = [
    "https://jobs.dayforcehcm.com/kgs/CANDIDATEPORTAL/api/JobPosting/GetJobPostings",
    "https://jobs.dayforcehcm.com/kgs/api/apply/v2/jobs",
    "https://jobs.dayforcehcm.com/kgs/en-US/CANDIDATEPORTAL/api/JobPosting/GetJobPostings",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": PORTAL,
}
KEYWORDS = {
    "network engineer", "network administrator", "network architect",
    "network manager", "it manager", "it director", "director of it",
    "director of information", "director of technology",
    "director of infrastructure", "director of operations",
    "director of security", "director of network",
    "information technology", "infrastructure manager",
    "infrastructure director", "systems engineer",
    "systems administrator", "cybersecurity", "security manager",
    "security engineer", "nist", "compliance", "grc",
}

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "jobs" / "data.json"
JOBS_DIR = ROOT / "jobs"
ARCHIVE_DIR = ROOT / "jobs" / "archive"


# ── fetch ──────────────────────────────────────────────────────────────────

def fetch() -> list[dict]:
    for url in API_CANDIDATES:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                if "json" not in r.headers.get("Content-Type", ""):
                    continue
                return _parse(json.loads(r.read()))
        except Exception:
            continue
    return []


def _parse(data) -> list[dict]:
    rows = data if isinstance(data, list) else next(
        (data[k] for k in ("jobs", "Jobs", "results", "Results",
                            "jobPostings", "JobPostings", "data", "Data")
         if isinstance(data.get(k), list)), []
    )
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        title = (r.get("JobTitle") or r.get("jobTitle") or
                 r.get("title") or r.get("Title") or "").strip()
        if not title:
            continue
        url = (r.get("ApplyUrl") or r.get("applyUrl") or
               r.get("url") or r.get("Url") or PORTAL)
        if not url.startswith(("http://", "https://")):
            url = PORTAL
        out.append({
            "id": str(r.get("JobPostingId") or r.get("jobPostingId") or
                      r.get("Id") or r.get("id") or title),
            "title": title,
            "location": (r.get("Location") or r.get("location") or
                         r.get("City") or r.get("city") or "").strip(),
            "department": (r.get("Department") or r.get("department") or "").strip(),
            "url": url,
            "first_seen": datetime.now(timezone.utc).date().isoformat(),
        })
    return out


# ── data ───────────────────────────────────────────────────────────────────

def load() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save(jobs: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def merge(stored: list[dict], fetched: list[dict]) -> list[dict]:
    existing = {j["id"] for j in stored}
    text = lambda j: (j["title"] + " " + j.get("department", "")).lower()
    new = [j for j in fetched
           if j["id"] not in existing and any(k in text(j) for k in KEYWORDS)]
    return stored + new


# ── render ─────────────────────────────────────────────────────────────────

_CSS = """\
*,*::before,*::after{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;max-width:680px;
  margin:2rem auto;padding:0 1rem;color:#111;background:#fff}
h1{font-size:1.35rem;margin:0 0 .25rem}
.sub{font-size:.85rem;color:#555;margin:0 0 1.25rem}
.sub a{color:#1d4ed8}
nav{margin-bottom:1.25rem;font-size:.82rem}
nav a{color:#1d4ed8;margin-right:.75rem;text-decoration:none}
nav a:hover{text-decoration:underline}
article{padding:.85rem 0;border-bottom:1px solid #e5e7eb}
article:last-child{border:none}
h3{margin:0 0 .2rem;font-size:.97rem}
h3 a{color:#1d4ed8;text-decoration:none}
h3 a:hover{text-decoration:underline}
.meta{font-size:.82rem;color:#6b7280}
.none{color:#6b7280;font-size:.9rem}
@media(prefers-color-scheme:dark){
  body{background:#0f172a;color:#e2e8f0}
  h3 a,nav a,.sub a{color:#93c5fd}
  article{border-color:#1e293b}
  .meta,.sub,.none{color:#94a3b8}
}"""


def _card(j: dict) -> str:
    t = html.escape(j["title"])
    loc = html.escape(j.get("location") or "Remote / Virtual")
    dept = f" &middot; {html.escape(j['department'])}" if j.get("department") else ""
    u = html.escape(j["url"], quote=True)
    return (f'<article><h3><a href="{u}" target="_blank" rel="noopener noreferrer">{t}</a></h3>'
            f'<p class="meta">{loc}{dept}</p></article>')


def _page(title: str, heading: str, sub: str, nav_html: str, body: str) -> str:
    return (f'<!DOCTYPE html><html lang="en"><head>'
            f'<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title>'
            f'<style>{_CSS}</style></head><body>'
            f'<h1>{html.escape(heading)}</h1>'
            f'<p class="sub">{sub}</p>'
            f'{nav_html}{body}</body></html>')


def generate(jobs: list[dict]) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

    recent = sorted([j for j in jobs if j.get("first_seen", "") >= cutoff],
                    key=lambda j: j["first_seen"], reverse=True)
    older  = [j for j in jobs if j.get("first_seen", "") < cutoff]

    by_month: dict[str, list] = {}
    for j in older:
        by_month.setdefault(j["first_seen"][:7], []).append(j)

    months = sorted(by_month, reverse=True)
    arch_nav = "".join(f'<a href="archive/{html.escape(m)}.html">{m}</a>' for m in months)
    nav_html = f'<nav>{arch_nav}</nav>' if arch_nav else ""

    body = "".join(_card(j) for j in recent) or '<p class="none">No new matching jobs in the last 30 days.</p>'
    portal_link = f'<a href="{html.escape(PORTAL, quote=True)}" target="_blank" rel="noopener noreferrer">KGS portal ↗</a>'

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / "index.html").write_text(
        _page("KGS Jobs – Last 30 Days", "KGS Job Openings",
              f"Matching positions — last 30 days &middot; {portal_link}",
              nav_html, body)
    )

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    back = '<nav><a href="../index.html">← Current (30 days)</a></nav>'
    for month, mjobs in by_month.items():
        sorted_jobs = sorted(mjobs, key=lambda j: j["first_seen"], reverse=True)
        body = "".join(_card(j) for j in sorted_jobs)
        (ARCHIVE_DIR / f"{month}.html").write_text(
            _page(f"KGS Jobs – {month}", f"KGS Jobs — {month}", portal_link, back, body)
        )


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    stored = load()
    fetched = fetch()

    if not fetched:
        print("Warning: no jobs fetched — regenerating from stored data.", file=sys.stderr)
    else:
        updated = merge(stored, fetched)
        if len(updated) != len(stored):
            save(updated)
            print(f"Added {len(updated) - len(stored)} new job(s). Total: {len(updated)}")
        else:
            print(f"No new jobs. Total stored: {len(stored)}")
        stored = updated

    generate(stored)
    print("Pages written: jobs/index.html + archive/")


if __name__ == "__main__":
    main()
