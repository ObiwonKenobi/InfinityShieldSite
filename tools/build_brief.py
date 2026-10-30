#!/usr/bin/env python3
"""
Build the rolling 30 day threat brief for infinityshield.co.

Reads brief/data/current.json, refreshes the CISA KEV snapshot when the feed is
reachable (brief/data/kev.json, kept when it is not), writes brief/index.html,
and refreshes the period, lede, and figures shown on the home page between the
rolling-brief markers in index.html. Monthly archive pages are built by
tools/build_archive.py and are not touched here.

Usage (from the repo root):
  python3 tools/build_brief.py              build the page and update the home page
  python3 tools/build_brief.py --check      validate brief/data/current.json only
  python3 tools/build_brief.py --no-fetch   build without trying to refresh the KEV feed
"""
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import (  # noqa: E402
    ROOT, esc, head, nav, render_top, render_vulns, render_list,
    render_breaches, render_todo, render_sources,
)
import charts  # noqa: E402
import kev  # noqa: E402

DATA = ROOT / "brief" / "data" / "current.json"
OUT = ROOT / "brief" / "index.html"
HOME = ROOT / "index.html"

REQUIRED = ["period", "issued", "lede", "top", "vulns", "supply", "breaches", "other", "todo", "sources"]
LIMITS = {"top": (3, 3), "vulns": (6, 14), "supply": (1, 6), "breaches": (6, 15), "other": (1, 6), "todo": (5, 10), "sources": (10, 40)}
SEV = {"crit", "high", "med"}
EM_DASH = "—"
CVE_RE = r"CVE-\d{4}-\d{4,7}"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
PERIOD_RE = r"(\d{1,2}) ([A-Z][a-z]{2})(?: (\d{4}))? – (\d{1,2}) ([A-Z][a-z]{2}) (\d{4})"


def parse_period(period):
    m = re.fullmatch(PERIOD_RE, period)
    end = dt.date(int(m[6]), MONTHS[m[5]], int(m[4]))
    y1 = int(m[3]) if m[3] else (end.year if MONTHS[m[2]] <= MONTHS[m[5]] else end.year - 1)
    return dt.date(y1, MONTHS[m[2]], int(m[1])), end


def parse_day(s):
    d, mon, y = s.split()
    return dt.date(int(y), MONTHS[mon], int(d))


def fmt_day(d):
    return f"{d.day} {list(MONTHS)[d.month - 1]}"


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
        if "records" not in r:
            problems.append(f"breaches[{i}] missing records (integer, or null when no count was disclosed)")
        elif r["records"] is not None and (not isinstance(r["records"], int) or r["records"] < 0):
            problems.append(f"breaches[{i}] records must be a non-negative integer or null")
    for i, s in enumerate(d.get("sources", [])):
        if not s.get("title") or not str(s.get("url", "")).startswith("https://"):
            problems.append(f"sources[{i}] needs a title and an https URL")
    if EM_DASH in json.dumps(d, ensure_ascii=False):
        problems.append("em dash found; use a comma, colon, or full stop instead")
    if not re.fullmatch(PERIOD_RE, d.get("period", "")):
        problems.append('period must look like "29 Sep – 28 Oct 2026" (en dash between dates)')
    if not re.fullmatch(r"\d{1,2} [A-Z][a-z]{2} \d{4}", d.get("issued", "")):
        problems.append('issued must look like "28 Oct 2026"')
    return problems


def compute_stats(d, kev_summary):
    vulns = d["vulns"]
    cves = sorted(set(re.findall(CVE_RE, json.dumps(d["top"]) + json.dumps(vulns))))
    exploited = [r for r in vulns if re.match(r"exploited\b", r["status"], re.I)]
    sev = Counter(r["sev"] for r in vulns)
    disclosed = [b for b in d["breaches"] if b.get("records")]
    records = sum(b["records"] for b in disclosed)
    return {
        "cves": cves,
        "items": len(d["top"]) + len(vulns),
        "vuln_rows": len(vulns),
        "exploited_rows": len(exploited),
        "sev": sev,
        "breaches": len(d["breaches"]),
        "disclosed": len(disclosed),
        "records": records,
        "supply": len(d["supply"]),
        "kev": kev_summary,
    }


def render_numbers(d, s):
    tiles = [
        ("CVEs tracked", str(len(s["cves"])), f'{s["items"]} items across the brief'),
        ("Confirmed exploited", f'{s["exploited_rows"]} of {s["vuln_rows"]}', "rows in the vulnerability table"),
    ]
    if s["kev"]:
        tiles.append(("Added to CISA KEV", str(s["kev"]["in_window_count"]), f'{len(s["kev"]["in_brief_and_kev"])} of them covered in this brief'))
    tiles += [
        ("Breaches listed", str(s["breaches"]), f'{s["disclosed"]} with a disclosed count'),
        ("People or records exposed", charts.compact(s["records"]), f'across {s["disclosed"]} disclosed breaches'),
        ("Supply chain incidents", str(s["supply"]), ""),
    ]
    parts = [("Critical", s["sev"].get("crit", 0), "sev-crit"), ("High", s["sev"].get("high", 0), "sev-high"), ("Medium", s["sev"].get("med", 0), "sev-med")]
    ranked = sorted(((b["org"], b["records"], f'{b["org"]}: {b["scale"]}') for b in d["breaches"] if b.get("records")), key=lambda r: -r[1])
    undisclosed = [b["org"] for b in d["breaches"] if not b.get("records")]
    note = ("No count disclosed: " + ", ".join(undisclosed) + ".") if undisclosed else ""
    return "\n".join([
        '  <section aria-labelledby="numbers">',
        '    <h2 id="numbers">By the numbers</h2>',
        charts.kpi_row(tiles),
        '    <div class="viz-row">',
        charts.segmented(parts, f'Severity of the {s["vuln_rows"]} vulnerabilities in the table'),
        charts.meter(s["exploited_rows"], s["vuln_rows"], "Confirmed exploited in the wild", "the rest are exploit attempts or proof of concept"),
        '    </div>',
        charts.ranked_bars(ranked, "Breaches by people or records affected", note),
        '  </section>',
    ])


def render_kev(k, window):
    start, end = window
    tiles = [
        ("Added this window", str(k["in_window_count"]), f"{fmt_day(start)} to {fmt_day(end)}"),
        ("Linked to ransomware", str(k["ransomware_in_window"]), "of this window's additions"),
        ("Federal due dates in 14 days", str(len(k["due_soon"])), "BOD 22-01 remediation deadlines"),
        ("From this brief, in KEV", str(len(k["in_brief_and_kev"])), ", ".join(k["in_brief_and_kev"][:3]) + (" …" if len(k["in_brief_and_kev"]) > 3 else "")),
    ]
    out = [
        '  <section aria-labelledby="kev">',
        '    <h2 id="kev">CISA Known Exploited Vulnerabilities</h2>',
        '    <p>What the US government has confirmed as exploited, from the CISA KEV catalog. Additions carry a remediation deadline for federal civilian agencies under BOD 22-01, and most contractors treat them the same way.</p>',
        charts.kpi_row(tiles),
        charts.columns(k["weekly"], "KEV additions per week, last 12 weeks", lambda b: f'{fmt_day(b["start"])} to {fmt_day(b["end"])}'),
    ]
    if k["due_soon"]:
        out += [
            '    <div class="tbl"><table>',
            '      <thead><tr><th>CVE</th><th>Vendor and product</th><th>Added</th><th>Due</th><th>Ransomware</th></tr></thead>',
            '      <tbody>',
        ]
        for e in k["due_soon"]:
            ransom = "Known" if str(e.get("knownRansomwareCampaignUse", "")).lower() == "known" else ""
            out.append(
                f'        <tr><td class="mono">{esc(e["cveID"])}</td><td>{esc(e["vendorProject"])} {esc(e["product"])}</td>'
                f'<td class="mono">{esc(e["dateAdded"])}</td><td class="mono">{esc(e["dueDate"])}</td><td>{ransom}</td></tr>'
            )
        out += ['      </tbody>', '    </table></div>']
    out.append(f'    <p class="label">Source: CISA KEV catalog version {esc(k["catalog_version"])}, {esc(k["total_count"])} entries, snapshot {esc(k["snapshot_date"])}.</p>')
    out.append('  </section>')
    return "\n".join(out)


def build_page(d, s, window):
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
    blocks = [
        render_numbers(d, s),
        render_top(d["top"]),
        render_vulns(d["vulns"]),
    ]
    if s["kev"]:
        blocks.append(render_kev(s["kev"], window))
    blocks += [
        render_list("supply", "Supply chain", d["supply"]),
        render_breaches(d["breaches"], d.get("unverified", "")),
        render_list("other", "Law enforcement and research", d["other"]),
        render_todo(d["todo"], "What to do this week"),
        render_sources(d["sources"]),
    ]
    for block in blocks:
        parts += ["", block]
    parts += [
        "",
        f'  <footer>Compiled from public reporting as of {esc(d["issued"])}. Figures are as first reported and may be revised. '
        "This brief covers the last 30 days and is refreshed every Monday; the calendar-month record is in the "
        '<a href="/archive/">archive</a>. · <a href="/">Home</a> · <a href="/about.html">About Infinity Shield</a></footer>',
        "</div>",
        "",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


def update_home(d, s):
    tiles = [
        ("CVEs tracked", str(len(s["cves"]))),
        ("Confirmed exploited", f'{s["exploited_rows"]} of {s["vuln_rows"]}'),
        ("Breaches", str(s["breaches"])),
        ("Records exposed", charts.compact(s["records"])),
    ]
    if s["kev"]:
        tiles.insert(2, ("Added to CISA KEV", str(s["kev"]["in_window_count"])))
    stat_html = "".join(f'<div class="stat"><div class="stat-v">{esc(v)}</div><div class="stat-l">{esc(l)}</div></div>' for l, v in tiles)
    band = (
        "<!-- rolling-brief:start -->\n"
        f'          <p class="brief-meta">Rolling 30 days · {esc(d["period"])} · Refreshed weekly</p>\n'
        "          <h2>Current Threat Brief</h2>\n"
        f'          <p>{esc(d["lede"])}</p>\n'
        f'          <div class="band-stats" aria-label="This brief in numbers">{stat_html}</div>\n'
        "          <!-- rolling-brief:end -->"
    )
    text = HOME.read_text(encoding="utf-8")
    text, n = re.subn(r"<!-- rolling-brief:start -->.*?<!-- rolling-brief:end -->", lambda m: band, text, flags=re.S)
    if n != 1:
        sys.exit("index.html: rolling-brief markers not found exactly once")
    HOME.write_text(text, encoding="utf-8")


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
    window = parse_period(d["period"])
    if "--no-fetch" not in sys.argv:
        kev.refresh()
    snap = kev.load()
    summary = None
    if snap:
        summary = kev.summarize(snap, window[0], window[1], json.dumps(d), today=parse_day(d["issued"]))
    else:
        print("kev: no snapshot available, KEV section omitted", file=sys.stderr)
    s = compute_stats(d, summary)
    OUT.write_text(build_page(d, s, window), encoding="utf-8")
    print("built brief/index.html")
    update_home(d, s)
    print("updated index.html (period, lede, figures)")


if __name__ == "__main__":
    main()
