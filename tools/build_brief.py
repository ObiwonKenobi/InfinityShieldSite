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
  python3 tools/build_brief.py --since FILE record what changed against last week's current.json (FILE), then build
"""
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_archive import (  # noqa: E402
    ROOT, esc, head, nav, render_top, render_vulns, render_list, render_outages, render_unverified,
    render_breaches, render_todo, render_sources,
)
import charts  # noqa: E402
from timeline import render_history  # noqa: E402
import changes  # noqa: E402
import traffic  # noqa: E402
import kev  # noqa: E402

DATA = ROOT / "brief" / "data" / "current.json"
OUT = ROOT / "brief" / "index.html"
HOME = ROOT / "index.html"

REQUIRED = ["period", "issued", "lede", "top", "vulns", "supply", "breaches", "other", "todo", "sources"]
LIMITS = {"top": (3, 3), "vulns": (6, 16), "supply": (1, 6), "breaches": (6, 15), "other": (1, 6), "outages": (0, 6), "todo": (5, 10), "sources": (10, 45)}
SEV = {"crit", "high", "med"}
TIMELINE_KEYS = ["vulns", "supply", "breaches", "other", "outages"]
TIMELINE_LANES = [
    ("vulns", "Vulnerabilities", "product"), ("supply", "Supply chain", "label"), ("breaches", "Breaches", "org"),
    ("other", "Law enforcement, research", "label"), ("outages", "Outages, no attack", "label"),
]
EM_DASH = "—"
CVE_RE = r"CVE-\d{4}-\d{4,7}"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
PERIOD_RE = r"(\d{1,2}) ([A-Z][a-z]{2})(?: (\d{4}))? – (\d{1,2}) ([A-Z][a-z]{2}) (\d{4})"


def parse_period(period):
    m = re.fullmatch(PERIOD_RE, period)
    end = dt.date(int(m[6]), MONTHS[m[5]], int(m[4]))
    y1 = int(m[3]) if m[3] else (end.year if MONTHS[m[2]] <= MONTHS[m[5]] else end.year - 1)
    return dt.date(y1, MONTHS[m[2]], int(m[1])), end


def parse_iso(v):
    try:
        return dt.date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


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
    for i, r in enumerate(d.get("outages", [])):
        for k in ("label", "basis", "text"):
            if not r.get(k):
                problems.append(f"outages[{i}] missing {k}")
    for cat in TIMELINE_KEYS:
        for i, r in enumerate(d.get(cat, [])):
            w = parse_iso(r.get("when"))
            if not w:
                problems.append(f"{cat}[{i}] needs when as YYYY-MM-DD (the day it became public or confirmed)")
                continue
            t = parse_iso(r["to"]) if r.get("to") else None
            if r.get("to") and (not t or t < w):
                problems.append(f"{cat}[{i}] to must be YYYY-MM-DD and not before when")
            try:
                end = parse_period(d["period"])[1]
            except Exception:
                continue
            if w > end or (t and t > end):
                problems.append(f"{cat}[{i}] date is after the end of the window")
    ch = d.get("changes")
    if ch and ch.get("run") != d.get("issued"):
        problems.append("changes block is from an earlier run; rerun with --since <last week's current.json> or remove it")
    unv = d.get("unverified", "")
    if isinstance(unv, list):
        for i, r in enumerate(unv):
            if not r.get("item") or not r.get("why"):
                problems.append(f"unverified[{i}] needs item and why")
            elif len(r["why"].split()) > 30:
                problems.append(f"unverified[{i}] why is over 30 words; keep it to one short line")
    elif not isinstance(unv, str):
        problems.append("unverified must be a list of {item, why} or a string")
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


def render_timeline(d, window):
    start, end = window
    days = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    lanes, total = [], Counter()
    for cat, name, field in TIMELINE_LANES:
        by_day, before = {}, 0
        for it in d.get(cat, []):
            w = parse_iso(it.get("when"))
            if not w:
                continue
            last = parse_iso(it.get("to")) or w
            if w < start:
                before += 1
            for n in range((max(w, start) - start).days, (min(last, end) - start).days + 1):
                by_day.setdefault(days[n], []).append(it[field].split(" · ")[0] if cat == "vulns" else it[field])
        lanes.append((cat, name, by_day, before))
        for day, names in by_day.items():
            total[day] += len(names)
    rows = []
    for cat, name, by_day, before in lanes:
        cells = []
        for day in days:
            names = by_day.get(day, [])
            n = len(names)
            tip = f"{fmt_day(day)}: {n} " + ("item" if n == 1 else "items") + ": " + "; ".join(names) if n else f"{fmt_day(day)}: none"
            cells.append(f'<span class="tl-c n{min(n, 3)}" title="{esc(tip).replace(chr(34), "&quot;")}">{n or ""}</span>')
        count = sum(len(v) for v in by_day.values())
        rows.append(f'        <div class="tl-row"><div class="tl-name">{esc(name)}</div><div class="tl-cells" style="--n:{len(days)}">{"".join(cells)}</div></div>')
    axis = "".join(
        f'<span class="tl-a{" we" if day.weekday() >= 5 else ""}">{day.day}{"<b>" + list(MONTHS)[day.month - 1] + "</b>" if day == start or day.day == 1 else ""}</span>'
        for day in days
    )
    busiest = [(day, n) for day, n in sorted(total.items(), key=lambda kv: (-kv[1], kv[0])) if n >= 3][:4]
    weeks = Counter()
    for day, n in total.items():
        weeks[(day - start).days // 7] += n
    wk_sorted = sorted(weeks.items(), key=lambda kv: -kv[1])
    out = [
        '  <section aria-labelledby="timeline">',
        '    <h2 id="timeline">Timeline</h2>',
        '    <p>Every dated item in this brief, by day and category. Darker cells mean more items that day, and a range such as an outage across two days fills each day it covers. Dates are when an item became public or was confirmed, not necessarily when the activity began.</p>',
        '    <div class="tl" tabindex="0" role="region" aria-label="Timeline chart, scrollable. The same information is listed below the chart.">',
        '      <div class="tl-grid" aria-hidden="true">',
        *rows,
        f'        <div class="tl-row"><div class="tl-name"></div><div class="tl-cells tl-axis" style="--n:{len(days)}">{axis}</div></div>',
        '      </div>',
        '    </div>',
    ]
    notes = []
    if busiest:
        notes.append("Busiest days: " + ", ".join(f"{fmt_day(day)} ({n} items)" for day, n in busiest) + ".")
    if wk_sorted:
        w0, n0 = wk_sorted[0]
        ws = start + dt.timedelta(w0 * 7)
        notes.append(f"Busiest week: {fmt_day(ws)} to {fmt_day(min(ws + dt.timedelta(6), end))} with {n0} dated items.")
    pre = sum(b for _, _, _, b in lanes)
    if pre:
        notes.append(f"{pre} item{'s' if pre != 1 else ''} began before the window and {'are' if pre != 1 else 'is'} drawn on its first day.")
    if notes:
        out.append('    <p class="viz-note">' + " ".join(esc(n) for n in notes) + '</p>')
    out.append('    <details class="tl-list"><summary>Timeline as a list</summary>')
    for cat, name, field in TIMELINE_LANES:
        items = sorted((it for it in d.get(cat, []) if parse_iso(it.get("when"))), key=lambda it: it["when"])
        if not items:
            continue
        out.append(f'      <p class="label">{esc(name)}</p><ul>')
        for it in items:
            w = parse_iso(it["when"])
            rng = fmt_day(w) + (f" to {fmt_day(parse_iso(it['to']))}" if it.get("to") else "")
            out.append(f'        <li><span class="mono">{esc(rng)}</span> {esc(it[field])}</li>')
        out.append('      </ul>')
    out += ['    </details>', '  </section>']
    return "\n".join(out)


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
            '    <div class="tbl" tabindex="0" role="region" aria-label="CISA KEV deadlines, scrollable table"><table>',
            '      <thead><tr><th>CVE</th><th>Vendor and product</th><th>Added</th><th>Due</th><th>Ransomware</th></tr></thead>',
            '      <tbody>',
        ]
        for e in k["due_soon"]:
            ransom = "Known" if str(e.get("knownRansomwareCampaignUse", "")).lower() == "known" else ""
            out.append(
                f'        <tr><td class="mono" data-label="CVE">{esc(e["cveID"])}</td><td data-label="Vendor and product">{esc(e["vendorProject"])} {esc(e["product"])}</td>'
                f'<td class="mono" data-label="Added">{esc(e["dateAdded"])}</td><td class="mono" data-label="Due">{esc(e["dueDate"])}</td><td data-label="Ransomware">{ransom}</td></tr>'
            )
        out += ['      </tbody>', '    </table></div>']
    out.append(f'    <p class="label">Source: CISA KEV catalog version {esc(k["catalog_version"])}, {esc(k["total_count"])} entries, snapshot {esc(k["snapshot_date"])}.</p>')
    out.append('  </section>')
    return "\n".join(out)


TOC_LABELS = {
    "new": "New this week", "numbers": "By the numbers", "timeline": "Timeline", "history": "Month by month", "top": "Top items", "vulns": "Exploited vulnerabilities", "kev": "CISA KEV",
    "supply": "Supply chain", "breaches": "Data breaches", "other": "Law enforcement, research",
    "outages": "Outages, no attack", "unverified": "Unverified claims", "do": "What to do", "src": "Sources",
}


def build_page(d, s, window):
    title = "Current Threat Brief | Infinity Shield"
    description = f'Rolling 30 day cybersecurity brief, {d["period"]}. {d["lede"]}'
    # An empty marker element lets CSS switch to the phone layout (":target" with ":has"), so the toggle needs no script and no second page.
    top = head(title, description, traffic.config()).replace("<body>", '<body>\n<span id="mobile-view"></span>', 1)
    parts = [top, nav("brief"), '<main id="main" class="wrap wide">', '  <header>']
    parts.append(
        '    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>Rolling 30 days</span>'
        f'<span>Period {esc(d["period"])}</span><span>Issued {esc(d["issued"])}</span><span>Refreshed weekly</span>'
        + (f'<span>{esc(traffic.line(traffic.load()))}</span>' if traffic.load() else "") +
        '<span class="viewtoggle"><a class="vt-m" href="#mobile-view">Mobile view</a><a class="vt-d" href="#desktop-view">Desktop view</a></span></div>'
    )
    parts.append('    <h1>Current <span>Threat Brief</span></h1>')
    parts.append(f'    <p class="lede">{esc(d["lede"])}</p>')
    parts.append('  </header>')
    unv = d.get("unverified", "")
    blocks = [
        *([changes.render(d)] if d.get("changes") else []),
        render_numbers(d, s),
        render_timeline(d, window),
        render_history(d, window[1]),
        render_top(d["top"]),
        render_vulns(d["vulns"]),
    ]
    if s["kev"]:
        blocks.append(render_kev(s["kev"], window))
    blocks += [
        render_list("supply", "Supply chain", d["supply"]),
        render_breaches(d["breaches"], unv if isinstance(unv, str) else ""),
        render_list("other", "Law enforcement and research", d["other"]),
        *([render_outages(d["outages"])] if d.get("outages") else []),
        *([render_unverified(unv)] if isinstance(unv, list) and unv else []),
        render_todo(d["todo"], "What to do this week"),
        render_sources(d["sources"]),
    ]
    toc = ['  <nav class="toc" aria-label="On this page"><p class="label">On this page</p><ul>']
    for block in blocks:
        for sid, text in re.findall(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', block):
            toc.append(f'    <li><a href="#{sid}">{TOC_LABELS.get(sid, text)}</a></li>')
    toc.append('  </ul></nav>')
    parts += ['<div class="layout">', "\n".join(toc), '<div class="content">']
    for block in blocks:
        parts += ["", block]
    parts += ["</div>", "</div>"]
    parts += [
        "",
        f'  <footer>Compiled from public reporting as of {esc(d["issued"])}. Figures are as first reported and may be revised. '
        "This brief covers the last 30 days and is refreshed every Monday; the calendar-month record is in the "
        '<a href="/archive/">archive</a>. · <a href="/">Home</a> · <a href="/about.html">About Infinity Shield</a>'
        + (" · Visits to this page are counted with a self-hosted, cookieless analytics tool that stores no personal data and respects Do Not Track. "
           "A visit that loads the page once and leaves counts as zero seconds." if traffic.config() else "") + '</footer>',
        "</main>",
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
        + (f'          <p class="brief-meta"><a href="/brief/#new">New since {esc(d["changes"]["since"])}: {len(d["changes"]["added"])} added, {len(d["changes"]["updated"])} updated</a></p>\n' if d.get("changes") else "")
        +
        f'          <div class="band-stats" role="group" aria-label="This brief in numbers">{stat_html}</div>\n'
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
    if "--since" in sys.argv:
        prev = json.loads(Path(sys.argv[sys.argv.index("--since") + 1]).read_text(encoding="utf-8"))
        d["changes"] = changes.compute(prev, d, window[0])
        DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ch = d["changes"]
        print(f'changes since {ch["since"]}: {len(ch["added"])} added, {len(ch["updated"])} updated')
    if "--no-fetch" not in sys.argv:
        kev.refresh()
        traffic.refresh()
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
