"""
HTML chart fragments for the briefs. Plain HTML and CSS, no scripts; the
styles live in brief.css under the "Data" comment. Every figure also has a
table or text twin on the page, so nothing is readable only through hover.
"""
import html


def esc(text):
    return html.escape(str(text), quote=True)


def compact(n):
    if n is None:
        return "n/a"
    n = float(n)
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            s = f"{n / div:.1f}".rstrip("0").rstrip(".")
            return s + suffix
    return f"{int(n):,}"


def kpi_row(tiles):
    """tiles: list of (label, value, sub). value is already formatted."""
    out = ['<div class="kpis" role="list">']
    for label, value, sub in tiles:
        out.append(
            f'<div class="kpi" role="listitem"><div class="kpi-v">{esc(value)}</div>'
            f'<div class="kpi-l">{esc(label)}</div>'
            + (f'<div class="kpi-s">{esc(sub)}</div>' if sub else "")
            + "</div>"
        )
    out.append("</div>")
    return "\n".join(out)


def segmented(parts, label):
    """Thin segmented bar. parts: list of (name, count, css_class)."""
    total = sum(c for _, c, _ in parts) or 1
    segs = "".join(
        f'<span class="seg-part {cls}" style="flex-basis:{c / total * 100:.2f}%" title="{esc(name)}: {c} of {total}"></span>'
        for name, c, cls in parts if c > 0
    )
    legend = "".join(f'<span class="lg"><i class="sw {cls}"></i>{esc(name)} <b>{c}</b></span>' for name, c, cls in parts)
    aria = ", ".join(f"{n} {c}" for n, c, _ in parts)
    return (
        f'<figure class="viz"><figcaption>{esc(label)}</figcaption>'
        f'<div class="seg" role="img" aria-label="{esc(label)}: {esc(aria)}">{segs}</div>'
        f'<div class="legend">{legend}</div></figure>'
    )


def meter(num, den, label, sub=""):
    pct = 0 if not den else num / den * 100
    tail = f" · {esc(sub)}" if sub else ""
    return (
        f'<figure class="viz"><figcaption>{esc(label)}</figcaption>'
        f'<div class="meter" role="img" aria-label="{esc(label)}: {num} of {den}" title="{num} of {den}"><span style="width:{pct:.1f}%"></span></div>'
        f'<div class="meter-t"><b>{num}</b> of {den}{tail}</div></figure>'
    )


def ranked_bars(rows, label, note=""):
    """Ranked horizontal bars, one hue. rows: list of (name, value, hover_title), largest first."""
    mx = max((v for _, v, _ in rows), default=0) or 1
    out = [f'<figure class="viz bars"><figcaption>{esc(label)}</figcaption><div class="bars-body" role="img" aria-label="{esc(label)}">']
    for name, v, title in rows:
        out.append(
            f'<div class="bar-row" title="{esc(title)}"><span class="bar-n">{esc(name)}</span>'
            f'<span class="bar-t"><span class="bar" style="width:{v / mx * 100:.2f}%"></span></span>'
            f'<span class="bar-v">{esc(compact(v))}</span></div>'
        )
    out.append("</div>")
    if note:
        out.append(f'<p class="viz-note">{esc(note)}</p>')
    out.append("</figure>")
    return "\n".join(out)


def columns(buckets, label, fmt_range):
    """Weekly columns, one hue. buckets: list of dicts with start, end, count; oldest first."""
    mx = max((b["count"] for b in buckets), default=0) or 1
    last = buckets[-1]
    peak = max(buckets, key=lambda b: b["count"])
    out = [f'<figure class="viz"><figcaption>{esc(label)}</figcaption><div class="cols" role="img" aria-label="{esc(label)}">']
    for b in buckets:
        h = b["count"] / mx * 100
        val = f'<span class="col-v">{b["count"]}</span>' if (b is last or b is peak) else ""
        out.append(f'<div class="col" title="{esc(fmt_range(b))}: {b["count"]}"><span class="col-bar" style="height:{h:.1f}%">{val}</span></div>')
    out.append("</div>")
    out.append(f'<div class="cols-axis"><span>{esc(fmt_range(buckets[0]))}</span><span>{esc(fmt_range(last))}</span></div></figure>')
    return "\n".join(out)
