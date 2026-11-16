"""What changed since the previous weekly run ("New this week").

The Monday run keeps last week's brief/data/current.json aside and runs
`python3 tools/build_brief.py --since <that file>`. That writes a `changes` block and an
`added` date on every item into the new current.json, so the page needs no git history and
the weekly gate (only current.json and the two built pages change) still holds.
"""
import datetime as dt
import html
import re

CATS = [
    ("top", "Top items", "top", "title"), ("vulns", "Vulnerabilities", "vulns", "product"),
    ("supply", "Supply chain", "supply", "label"), ("breaches", "Breaches", "breaches", "org"),
    ("other", "Law enforcement, research", "other", "label"), ("outages", "Outages, no attack", "outages", "label"),
]
SKIP = {"when", "to", "added"}
SHORT = {"status", "sev", "scale", "records", "basis", "cve", "note", "product", "org"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def esc(t):
    return html.escape(str(t), quote=False)


def key_of(cat, it, field):
    name = str(it.get(field, ""))
    if cat == "vulns" and it.get("cve"):
        m = re.search(r"CVE-\d{4}-\d{4,7}", it["cve"])
        if m:
            return m.group(0)
    if cat in ("top", "other", "supply", "outages"):
        name = name.split(":")[0]
    name = re.sub(r"\(.*?\)", "", name).split(",")[0]
    name = re.sub(r"\b\d{1,2}( (to|and) \d{1,2})? (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", "", name)
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def label_of(cat, it, field):
    name = str(it.get(field, ""))
    return name.split(":")[0] if cat == "top" else name


def iso(day_text):
    d, m, y = day_text.split()
    return dt.date(int(y), MONTHS.index(m) + 1, int(d)).isoformat()


def _shorten(v, n=48):
    v = str(v)
    return v if len(v) <= n else v[: n - 1] + "…"


def _name_date(name, window_start):
    """Latest day named in an item's label, as ISO, for items that predate the `when` field."""
    days = []
    for d, m in re.findall(r"(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", name):
        y = window_start.year - (1 if MONTHS.index(m) + 1 > window_start.month + 6 else 0)
        days.append(dt.date(y, MONTHS.index(m) + 1, int(d)).isoformat())
    return max(days) if days else None


def _what(prev, cur):
    bits = []
    for k in cur:
        if k in SKIP or prev.get(k) == cur[k]:
            continue
        if k in SHORT:
            old = prev.get(k)
            old = "blank" if old in (None, "") else old
            new = "blank" if cur[k] in (None, "") else cur[k]
            bits.append(f"{k} was {_shorten(old)}, now {_shorten(new)}")
        else:
            bits.append("text revised")
    out = []
    for b in bits:
        if b not in out:
            out.append(b)
    return "; ".join(out[:3])


def compute(prev, cur, window_start):
    """Return the changes block and set `added` on every current item."""
    since_iso = iso(prev["issued"])
    block = {"since": prev["issued"], "run": cur["issued"], "added": [], "updated": [], "dropped": []}
    for cat, name, _sid, field in CATS:
        old = {key_of(cat, it, field): it for it in prev.get(cat, [])}
        seen = set()
        for it in cur.get(cat, []):
            k = key_of(cat, it, field)
            seen.add(k)
            if k in old:
                it["added"] = old[k].get("added") or since_iso
                what = _what(old[k], it)
                if what:
                    block["updated"].append({"cat": cat, "name": label_of(cat, it, field), "what": what})
            else:
                it["added"] = iso(cur["issued"])
                block["added"].append({"cat": cat, "name": label_of(cat, it, field)})
        for k, it in old.items():
            if k not in seen:
                when = it.get("to") or it.get("when") or _name_date(label_of(cat, it, field), window_start)
                reason = "Older than the window" if when and when < window_start.isoformat() else "Left the brief"
                block["dropped"].append({"cat": cat, "name": label_of(cat, it, field), "why": reason})
    return block


def render(d):
    ch = d.get("changes")
    if not ch:
        return ""
    names = {c: n for c, n, _s, _f in CATS}
    sids = {c: s for c, _n, s, _f in CATS}
    a, u, x = ch.get("added", []), ch.get("updated", []), ch.get("dropped", [])
    out = [
        '  <section aria-labelledby="new">',
        '    <h2 id="new">New this week</h2>',
        f'    <p>Changes since the brief issued {esc(ch["since"])}: <strong>{len(a)} added</strong>, <strong>{len(u)} updated</strong>, <strong>{len(x)} dropped</strong>. '
        'Dropped items usually aged out of the 30 day window; the earlier versions stay in the archive.</p>',
    ]
    def group(title, rows, fmt):
        if not rows:
            return
        out.append(f'    <p class="label">{esc(title)} ({len(rows)})</p>')
        out.append('    <ul class="list newlist">')
        for r in rows:
            out.append("      " + fmt(r))
        out.append('    </ul>')
    group("Added", a, lambda r: f'<li><a href="#{sids[r["cat"]]}">{esc(r["name"])}</a> <span class="basis">{esc(names[r["cat"]])}</span></li>')
    group("Updated", u, lambda r: f'<li><a href="#{sids[r["cat"]]}">{esc(r["name"])}</a> <span class="basis">{esc(r["what"])}</span></li>')
    group("Dropped", x, lambda r: f'<li>{esc(r["name"])} <span class="basis">{esc(names[r["cat"]])}: {esc(r["why"])}</span></li>')
    out.append('  </section>')
    return "\n".join(out)
