#!/usr/bin/env python3
"""
Build the monthly threat brief archive for infinityshield.co.

Reads one JSON file per calendar month from archive/data/YYYY-MM.json and writes:
  archive/YYYY-MM.html   one page per month, same layout as the 30 day brief on the home page
  archive/index.html     the archive listing, newest month first

The 30 day rolling brief (index.html) is not touched by this script.
Styling comes from /brief.css, which was lifted from the home page.

Usage (from the repo root):  python3 tools/build_archive.py
"""
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "archive" / "data"
OUT = ROOT / "archive"

SEV_CLASSES = {"crit", "high", "med"}


def esc(text):
    """Escape text for HTML element content."""
    return html.escape(str(text), quote=False)


def attr(text):
    """Escape text for an HTML attribute value."""
    return html.escape(str(text), quote=True)


def sev_class(value):
    """Only allow the three severity classes the stylesheet knows."""
    return value if value in SEV_CLASSES else "high"


def nav(current):
    """Site nav, matching the home page. current is 'archive' for archive pages."""
    def link(href, label, key):
        cur = ' aria-current="page"' if key == current else ""
        return f'      <li><a href="{href}"{cur}>{label}</a></li>'
    return "\n".join([
        '<nav class="site-nav" aria-label="Main navigation">',
        '  <div class="site-nav-inner">',
        '    <a href="/" class="site-brand"><img src="/logo-transparent.png" alt="">Infinity Shield</a>',
        '    <ul class="site-links">',
        link("/", "Threat Brief", "home"),
        link("/archive/", "Archive", "archive"),
        link("/about.html", "About", "about"),
        '    </ul>',
        '  </div>',
        '</nav>',
    ])


def head(title, description):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{attr(description)}">
<style>*,*::before,*::after{{box-sizing:border-box}}body{{margin:0}}img{{max-width:100%}}</style><title>{esc(title)}</title>
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Public+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="/brief.css">
</head>
<body>
<div class="circuit-bg" aria-hidden="true"></div>
"""


def render_top(items):
    out = ['  <section class="lead" aria-labelledby="top">', '    <h2 id="top">Top items</h2>']
    for it in items:
        out.append('')
        out.append('    <article class="item">')
        out.append(
            f'      <div class="item-head"><h3>{esc(it["title"])}</h3>'
            f'<span class="sev {sev_class(it.get("sev"))}">{esc(it["status"])}</span></div>'
        )
        out.append(f'      <p>{esc(it["body"])}</p>')
        facts = it.get("facts") or []
        if facts:
            out.append('      <dl class="facts">')
            for name, value in facts:
                value_html = "<br>".join(esc(v) for v in str(value).split("\n"))
                out.append(f'        <div><dt>{esc(name)}</dt><dd class="mono">{value_html}</dd></div>')
            out.append('      </dl>')
        out.append(f'      <p class="action"><b>Action:</b> {esc(it["action"])}</p>')
        out.append('    </article>')
    out.append('  </section>')
    return "\n".join(out)


def render_vulns(rows):
    out = [
        '  <section aria-labelledby="vulns">',
        '    <h2 id="vulns">Exploited vulnerabilities and zero-days</h2>',
        '    <div class="tbl"><table>',
        '      <thead><tr><th>Product</th><th>CVE</th><th>What it allows</th><th>Status</th></tr></thead>',
        '      <tbody>',
    ]
    for r in rows:
        note = f'<br>{esc(r["note"])}' if r.get("note") else ""
        out.append(
            f'        <tr><td>{esc(r["product"])}</td><td class="mono">{esc(r["cve"])}</td>'
            f'<td>{esc(r["allows"])}</td>'
            f'<td><span class="sev {sev_class(r.get("sev"))}">{esc(r["status"])}</span>{note}</td></tr>'
        )
    out += ['      </tbody>', '    </table></div>', '  </section>']
    return "\n".join(out)


def render_list(section_id, heading, rows):
    out = [f'  <section aria-labelledby="{section_id}">', f'    <h2 id="{section_id}">{esc(heading)}</h2>', '    <ul class="list">']
    for r in rows:
        out.append(f'      <li><span class="label">{esc(r["label"])}</span><p>{esc(r["text"])}</p></li>')
    out += ['    </ul>', '  </section>']
    return "\n".join(out)


def render_breaches(rows, unverified):
    out = [
        '  <section aria-labelledby="breaches">',
        '    <h2 id="breaches">Data breaches</h2>',
        '    <div class="tbl"><table>',
        '      <thead><tr><th>Organization</th><th>People / records</th><th>Cause and data</th></tr></thead>',
        '      <tbody>',
    ]
    for r in rows:
        out.append(
            f'        <tr><td>{esc(r["org"])}</td><td>{esc(r["scale"])}</td><td>{esc(r["cause"])}</td></tr>'
        )
    out += ['      </tbody>', '    </table></div>']
    if unverified:
        out.append(f'    <p class="label">Unverified claims: {esc(unverified)}</p>')
    out.append('  </section>')
    return "\n".join(out)


def render_todo(items, label):
    out = ['  <section aria-labelledby="do">', f'    <h2 id="do">{esc(label)}</h2>', '    <ol class="todo">']
    out += [f'      <li>{esc(i)}</li>' for i in items]
    out += ['    </ol>', '  </section>']
    return "\n".join(out)


def render_sources(sources):
    out = ['  <section aria-labelledby="src">', '    <h2 id="src">Sources</h2>', '    <ul class="sources">']
    for s in sources:
        out.append(f'      <li><a href="{attr(s["url"])}">{esc(s["title"])}</a></li>')
    out += ['    </ul>', '  </section>']
    return "\n".join(out)


def build_month(data):
    label = data["label"]
    title = f"{label} Threat Brief | Infinity Shield"
    description = f'Cybersecurity brief for {data["period"]}. {data["lede"]}'
    parts = [head(title, description), nav("archive"), '<div class="wrap">', '  <header>']
    parts.append(
        f'    <div class="marking"><span class="tlp">TLP:CLEAR</span>'
        f'<span>Period {esc(data["period"])}</span><span>Issued {esc(data["issued"])}</span></div>'
    )
    month_name, year = label.rsplit(" ", 1)
    parts.append(f'    <h1>{esc(month_name)} {esc(year)} <span>Threat Brief</span></h1>')
    parts.append(f'    <p class="lede">{esc(data["lede"])}</p>')
    parts.append('  </header>')
    parts.append('')
    parts.append(render_top(data["top"]))
    parts.append('')
    parts.append(render_vulns(data["vulns"]))
    parts.append('')
    parts.append(render_list("supply", "Supply chain", data["supply"]))
    parts.append('')
    parts.append(render_breaches(data["breaches"], data.get("unverified", "")))
    parts.append('')
    parts.append(render_list("other", "Law enforcement and research", data["other"]))
    parts.append('')
    parts.append(render_todo(data["todo"], "What to do"))
    parts.append('')
    parts.append(render_sources(data["sources"]))
    parts.append('')
    parts.append(
        f'  <footer>Compiled from public reporting as of {esc(data["issued"])}. '
        'Figures are as first reported and may be revised. · '
        '<a href="/archive/">All months</a> · <a href="/">Current 30 day brief</a> · '
        '<a href="/about.html">About Infinity Shield</a></footer>'
    )
    parts.append('</div>')
    parts.append('')
    parts.append('</body>')
    parts.append('</html>')
    return "\n".join(parts) + "\n"


def build_index(months):
    """months is a list of data dicts, newest first."""
    parts = [
        head(
            "Archive | Infinity Shield",
            "Monthly cybersecurity threat briefs, one per calendar month. The current 30 day brief is on the home page.",
        ),
        nav("archive"),
        '<div class="wrap">',
        '  <header>',
        '    <div class="marking"><span class="tlp">TLP:CLEAR</span><span>Calendar month briefs</span></div>',
        '    <h1>Threat Brief <span>Archive</span></h1>',
        '    <p class="lede">One brief for each calendar month, added after the month closes. The rolling 30 day brief stays on the <a href="/">home page</a> and is not archived here.</p>',
        '  </header>',
        '',
        '  <section aria-labelledby="months">',
        '    <h2 id="months">Months</h2>',
        '    <ul class="list">',
    ]
    for m in months:
        parts.append(
            f'      <li><a class="label" href="/archive/{attr(m["month"])}.html">{esc(m["label"])}</a>'
            f'<p>{esc(m["lede"])}</p></li>'
        )
    parts += [
        '    </ul>',
        '  </section>',
        '',
        '  <footer>Compiled from public reporting. Figures are as first reported and may be revised. · '
        '<a href="/">Current 30 day brief</a> · <a href="/about.html">About Infinity Shield</a></footer>',
        '</div>',
        '',
        '</body>',
        '</html>',
    ]
    return "\n".join(parts) + "\n"


def main():
    files = sorted(DATA.glob("*.json"))
    if not files:
        sys.exit(f"No month data found in {DATA}")
    months = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("month") != f.stem:
            sys.exit(f'{f.name}: "month" field must equal the file name ({f.stem})')
        (OUT / f"{data['month']}.html").write_text(build_month(data), encoding="utf-8")
        months.append(data)
        print(f"built archive/{data['month']}.html")
    months.sort(key=lambda m: m["month"], reverse=True)
    (OUT / "index.html").write_text(build_index(months), encoding="utf-8")
    print("built archive/index.html")


if __name__ == "__main__":
    main()
