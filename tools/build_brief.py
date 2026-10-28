#!/usr/bin/env python3
"""
Build the rolling 30 day threat brief for infinityshield.co.

Reads brief/data/current.json and writes brief/index.html, then refreshes the
period and lede shown on the home page between the rolling-brief markers in
index.html. Monthly archive pages are built by tools/build_archive.py and are
not touched here.

Usage (from the repo root):
  python3 tools/build_brief.py            build the page and update the home page
  python3 tools/build_brief.py --check    validate brief/data/current.json only
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import (  # noqa: E402
    ROOT, esc, head, nav, render_top, render_vulns, render_list,
    render_breaches, render_todo, render_sources,
)

DATA = ROOT / "brief" / "data" / "current.json"
OUT = ROOT / "brief" / "index.html"
HOME = ROOT / "index.html"

REQUIRED = ["period", "issued", "lede", "top", "vulns", "supply", "breaches", "other", "todo", "sources"]
LIMITS = {"top": (3, 3), "vulns": (6, 14), "supply": (1, 6), "breaches": (6, 15), "other": (1, 6), "todo": (5, 10), "sources": (10, 40)}
SEV = {"crit", "high", "med"}
EM_DASH = "—"


def validate(d):
    problems = []
    for k in REQUIRED:
        if k not in d:
            problems.append(f"missing key: {k}")
    for k, (lo, hi) in LIMITS.items():
        n = len(d.get(k, []))
        if not lo <= n <= hi:
            problems.append(f"{k}: {n} items, expected {lo} to {hi}")
    for i, it in enumerate(d.get("top", [])):
        for k in ("title", "sev", "status", "body", "action"):
            if not it.get(k):
                problems.append(f"top[{i}] missing {k}")
        if it.get("sev") not in SEV:
            problems.append(f"top[{i}] sev must be one of {sorted(SEV)}")
    for i, r in enumerate(d.get("vulns", [])):
        for k in ("product", "cve", "allows", "sev", "status"):
            if not r.get(k):
                problems.append(f"vulns[{i}] missing {k}")
        if r.get("sev") not in SEV:
            problems.append(f"vulns[{i}] sev must be one of {sorted(SEV)}")
    for i, r in enumerate(d.get("breaches", [])):
        for k in ("org", "scale", "cause"):
            if not r.get(k):
                problems.append(f"breaches[{i}] missing {k}")
    for i, s in enumerate(d.get("sources", [])):
        if not s.get("title") or not str(s.get("url", "")).startswith("https://"):
            problems.append(f"sources[{i}] needs a title and an https URL")
    if EM_DASH in json.dumps(d, ensure_ascii=False):
        problems.append("em dash found; use a comma, colon, or full stop instead")
    if not re.fullmatch(r"\d{1,2} [A-Z][a-z]{2}( \d{4})? – \d{1,2} [A-Z][a-z]{2} \d{4}", d.get("period", "")):
        problems.append('period must look like "29 Sep – 28 Oct 2026" (en dash between dates)')
    return problems


def build_page(d):
    title = "Current Threat Brief | Infinity Shield"
    description = f'Rolling 30 day cybersecurity brief, {d["period"]}. {d["lede"]}'
    parts = [head(title, description), nav("brief"), '<div class="wrap">', '  <header>']
    parts.append(
        '    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>Rolling 30 days</span>'
        f'<span>Period {esc(d["period"])}</span><span>Issued {esc(d["issued"])}</span><span>Refreshed weekly</span></div>'
    )
    parts.append('    <h1>Current <span>Threat Brief</span></h1>')
    parts.append(f'    <p class="lede">{esc(d["lede"])}</p>')
    parts.append('  </header>')
    for block in (
        render_top(d["top"]),
        render_vulns(d["vulns"]),
        render_list("supply", "Supply chain", d["supply"]),
        render_breaches(d["breaches"], d.get("unverified", "")),
        render_list("other", "Law enforcement and research", d["other"]),
        render_todo(d["todo"], "What to do this week"),
        render_sources(d["sources"]),
    ):
        parts += ['', block]
    parts += [
        '',
        f'  <footer>Compiled from public reporting as of {esc(d["issued"])}. Figures are as first reported and may be revised. '
        'This brief covers the last 30 days and is refreshed every Monday; the calendar-month record is in the '
        '<a href="/archive/">archive</a>. · <a href="/">Home</a> · <a href="/about.html">About Infinity Shield</a></footer>',
        '</div>',
        '',
        '</body>',
        '</html>',
    ]
    return "\n".join(parts) + "\n"


def update_home(d):
    s = HOME.read_text(encoding="utf-8")
    band = (
        '<!-- rolling-brief:start -->\n'
        f'          <p class="brief-meta">Rolling 30 days · {esc(d["period"])} · Refreshed weekly</p>\n'
        '          <h2>Current Threat Brief</h2>\n'
        f'          <p>{esc(d["lede"])}</p>\n'
        '          <!-- rolling-brief:end -->'
    )
    s, n1 = re.subn(r'<!-- rolling-brief:start -->.*?<!-- rolling-brief:end -->', lambda m: band, s, flags=re.S)
    if n1 != 1:
        sys.exit("index.html: rolling-brief markers not found exactly once")
    HOME.write_text(s, encoding="utf-8")


def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    problems = validate(d)
    if problems:
        print("brief/data/current.json has problems:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    if "--check" in sys.argv:
        print("brief/data/current.json is valid")
        return
    OUT.write_text(build_page(d), encoding="utf-8")
    print("built brief/index.html")
    update_home(d)
    print("updated index.html (period and lede)")


if __name__ == "__main__":
    main()
