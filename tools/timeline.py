"""Weekly timeline ("longer view") shared by the brief page and the archive index.

Reads archive/data/*.json (read only). The brief passes its own data so days after the last
archived month are included; the archive index passes None and ends at the last archived month.
"""
import datetime as dt
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TIMELINE_LANES = [
    ("vulns", "Vulnerabilities", "product"), ("supply", "Supply chain", "label"), ("breaches", "Breaches", "org"),
    ("other", "Law enforcement, research", "label"), ("outages", "Outages, no attack", "label"),
]


def esc(text):
    return html.escape(str(text), quote=False)


def parse_iso(v):
    try:
        return dt.date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def fmt_day(d):
    return f"{d.day} {MONTH_NAMES[d.month - 1]}"


def month_end(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return (dt.date(y + (m == 12), m % 12 + 1, 1)) - dt.timedelta(1)


def render_history(d, end=None):
    """Weekly counts across the archived months plus this brief's days after the last archived month."""
    files = sorted((ROOT / "archive" / "data").glob("*.json"))
    if not files:
        return ""
    cats = [(c, n, f) for c, n, f in TIMELINE_LANES]
    rows = {c: [] for c, _, _ in cats}  # (date, name)
    undated = 0
    last_end = dt.date.min
    for f in files:
        a = json.loads(f.read_text(encoding="utf-8"))
        last_end = max(last_end, month_end(a["month"]))
        for c, _, field in cats:
            for it in a.get(c, []):
                w = parse_iso(it.get("when"))
                if w:
                    rows[c].append((w, it[field]))
                else:
                    undated += 1
    for c, _, field in cats:
        for it in (d or {}).get(c, []):
            w = parse_iso(it.get("when"))
            if w and w > last_end:
                rows[c].append((w, it[field]))
    end = end or last_end
    cats = [x for x in cats if rows[x[0]]]
    every = [w for c in rows for w, _ in rows[c]]
    first = min(every)
    first_mon = first - dt.timedelta(first.weekday())
    nweeks = (end - first_mon).days // 7 + 1
    weeks = [first_mon + dt.timedelta(7 * i) for i in range(nweeks)]
    grid = {c: [[] for _ in weeks] for c, _, _ in cats}
    for c in rows:
        for w, name in rows[c]:
            i = (w - first_mon).days // 7
            if 0 <= i < nweeks:
                grid[c][i].append(name)
    totals = [sum(len(grid[c][i]) for c in grid) for i in range(nweeks)]

    def level(n):
        return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 4 else 3

    def cell(names, label):
        n = len(names)
        shown = "; ".join(names[:6]) + (f"; and {n - 6} more" if n > 6 else "")
        tip = f"Week of {label}: {n} " + ("item" if n == 1 else "items") + (": " + shown if n else "")
        return f'<span class="tl-c n{level(n)}" title="{esc(tip).replace(chr(34), "&quot;")}">{n or ""}</span>'

    def lane(name, cells):
        return f'        <div class="tl-row"><div class="tl-name">{esc(name)}</div><div class="tl-cells" style="--n:{nweeks}">{"".join(cells)}</div></div>'

    def total_cell(t, w):
        lv = 0 if t == 0 else 1 if t <= 4 else 2 if t <= 9 else 3
        return f'<span class="tl-c n{lv}" title="Week of {fmt_day(w)}: {t} items">{t or ""}</span>'

    out_rows = [lane("All categories", [total_cell(t, w) for w, t in zip(weeks, totals)])]
    for c, name, _ in cats:
        out_rows.append(lane(name, [cell(grid[c][i], fmt_day(weeks[i])) for i in range(nweeks)]))
    axis, prev_m = [], None
    for w in weeks:
        mark = f"<b>{list(MONTH_NAMES)[w.month - 1]}</b>" if w.month != prev_m else ""
        prev_m = w.month
        axis.append(f'<span class="tl-a">{w.day}{mark}</span>')
    out_rows.append(f'        <div class="tl-row"><div class="tl-name"></div><div class="tl-cells tl-axis" style="--n:{nweeks}">{"".join(axis)}</div></div>')
    top = sorted(range(nweeks), key=lambda i: (-totals[i], i))[:3]
    notes = ["Busiest weeks (starting Monday): " + ", ".join(f"{fmt_day(weeks[i])} ({totals[i]} items)" for i in top) + "."]
    lead = (f"Archived months are counted in full through {fmt_day(last_end)}; the current brief supplies the days after that. " if d
            else f"Archived months only, through {fmt_day(last_end)}. ")
    tail = ("and the outages row only starts with the current brief because the archive did not track outages separately." if d
            else "and the archive did not track outages separately, so that row is left out.")
    notes.append(lead + f"{undated} archived item{'s' if undated != 1 else ''} without a reliable date {'are' if undated != 1 else 'is'} not plotted, " + tail)
    out = [
        '  <section aria-labelledby="history">',
        '    <h2 id="history">Longer view: month by month</h2>',
        '    <p>The same categories by week, from the first archived month' + (' to now' if d else ' to the latest') + '. The top row adds every category together, so a cluster shows as a run of dark cells. Dates are when an item was reported or confirmed; where an attack began earlier, the archive and brief text for that item says so.</p>',
        '    <div class="tl" tabindex="0" role="region" aria-label="Weekly timeline chart, scrollable. The same counts are in the table below the chart.">',
        '      <div class="tl-grid wk" aria-hidden="true">',
        *out_rows,
        '      </div>',
        '    </div>',
        '    <p class="viz-note">' + " ".join(esc(n) for n in notes) + '</p>',
        '    <details class="tl-list"><summary>Weekly counts as a table</summary>',
        '      <div class="tbl" tabindex="0" role="region" aria-label="Weekly counts, scrollable table"><table>',
        "      <thead><tr><th>Week of</th>" + "".join(f"<th>{esc(n)}</th>" for _, n, _ in cats) + "<th>Total</th></tr></thead><tbody>",
    ]
    for i, w in enumerate(weeks):
        out.append(f'        <tr><td class="mono" data-label="Week of">{fmt_day(w)}</td>' + "".join(
            f'<td data-label="{esc(n)}">{len(grid[c][i])}</td>' for c, n, _ in cats) + f'<td data-label="Total">{totals[i]}</td></tr>')
    out += ['      </tbody></table></div>', '    </details>', '  </section>']
    return "\n".join(out)


