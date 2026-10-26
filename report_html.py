"""PC vs Parts page: one self-contained HTML file (inline CSS + JS, no network) so it opens straight from disk."""
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

# badge tones: text always says what the colour means, colour is a second cue only
FLAG = {"check": "amber", "estimated": "slate", "manual": "blue", "can't value": "red"}
BASIS = {"manual": ("manual", "blue"), "estimated": ("estimated", "slate"), "none": ("can't value", "red")}
COLS = [("Deal", "num"), ("% of parts", "num"), ("Ask", "num"), ("Parts value", "num"), ("Buy-smart", "num"),
        ("With extras", "num"), ("Title", "text"), ("CPU", "text"), ("GPU", "text"), ("RAM", "text"),
        ("Flags", "text"), ("Seen", "num")]

# palette: ui-ux-pro-max "Analytics Dashboard" / Data-Dense Dashboard (same blue/green/amber as the Excel)
CSS = """
:root{color-scheme:light dark;--bg:#F8FAFC;--card:#FFFFFF;--text:#0F172A;--muted:#475569;--border:#E2E8F0;
--head:#1E40AF;--on-head:#FFFFFF;--link:#1E40AF;--ring:#D97706;--deal-row:#F0FDF4;
--green-bg:#DCFCE7;--green:#166534;--amber-bg:#FEF3C7;--amber:#92400E;--red-bg:#FEE2E2;--red:#991B1B;
--slate-bg:#F1F5F9;--slate:#334155;--blue-bg:#DBEAFE;--blue:#1E40AF}
@media (prefers-color-scheme:dark){:root{--bg:#0F172A;--card:#1E293B;--text:#E2E8F0;--muted:#94A3B8;--border:#334155;
--head:#1E3A8A;--link:#93C5FD;--ring:#F59E0B;--deal-row:#052E16;--green-bg:#14532D;--green:#BBF7D0;
--amber-bg:#78350F;--amber:#FDE68A;--red-bg:#7F1D1D;--red:#FECACA;--slate-bg:#334155;--slate:#E2E8F0;
--blue-bg:#1E3A8A;--blue:#DBEAFE}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1440px;margin:0 auto;padding:16px}
h1{margin:0;font-size:1.6rem}.sub{margin:0 0 12px;color:var(--muted)}
a{color:var(--link)}:focus-visible{outline:3px solid var(--ring);outline-offset:2px}
.chips{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:0 0 16px}
.chips li{background:var(--card);border:1px solid var(--border);border-radius:999px;padding:6px 14px}
.tools{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:12px}
.tools label{display:flex;align-items:center;gap:8px;min-height:44px;cursor:pointer}
.tools input[type=search]{font:inherit;min-height:44px;padding:0 12px;width:min(100%,320px);
background:var(--card);color:var(--text);border:1px solid var(--muted);border-radius:8px}
.tools input[type=checkbox]{width:20px;height:20px;accent-color:var(--head)}
#shown{color:var(--muted)}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--border);border-radius:12px}
table{border-collapse:collapse;width:100%}
th,td{padding:8px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--border)}
.builds thead th{background:var(--head);color:var(--on-head);white-space:nowrap}
.builds th button{font:inherit;font-weight:600;color:inherit;background:none;border:0;padding:4px 0;cursor:pointer;min-height:36px}
th[aria-sort=ascending] button::after{content:" \\25B2"}th[aria-sort=descending] button::after{content:" \\25BC"}
td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
tbody.deal tr.main{background:var(--deal-row)}tr.main:hover{outline:1px solid var(--border)}
button.more{font:inherit;color:var(--link);background:none;border:1px solid var(--border);border-radius:8px;
min-height:44px;min-width:44px;padding:0 10px;cursor:pointer;white-space:nowrap}
button.more::before{content:"\\25B8";display:inline-block;margin-right:4px;transition:transform .15s}
button.more[aria-expanded=true]::before{transform:rotate(90deg)}
.b{display:inline-block;border-radius:6px;padding:1px 8px;margin:1px 2px 1px 0;font-size:.875rem;font-weight:600;white-space:nowrap}
.green{background:var(--green-bg);color:var(--green)}.amber{background:var(--amber-bg);color:var(--amber)}
.red{background:var(--red-bg);color:var(--red)}.slate{background:var(--slate-bg);color:var(--slate)}
.blue{background:var(--blue-bg);color:var(--blue)}.plain{border:1px solid var(--border)}
tr.detail>td{background:var(--bg);padding:12px 16px}
.parts{background:var(--card);border:1px solid var(--border);border-radius:8px;min-width:480px}
.parts th{color:var(--muted);font-size:.875rem}.parts tr.sec th{color:var(--text)}
.parts tr.tot th,.parts tr.tot td{color:var(--text);font-weight:700;border-top:2px solid var(--border)}
.parts tr.grand th,.parts tr.grand td{background:var(--slate-bg)}
.detail h3{font-size:1rem;margin:12px 0 4px}.detail ul{margin:0;padding-left:20px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.empty{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px}
details.grp{margin-top:24px}details.grp>summary{cursor:pointer;min-height:44px;display:flex;align-items:center;gap:8px}
details.grp>summary h2{display:inline;font-size:1.2rem;margin:0}.grp .sub{margin:8px 0}
.mini-wrap{overflow-x:auto;background:var(--card);border:1px solid var(--border);border-radius:12px}
.mini{min-width:640px}.mini thead th{color:var(--muted);font-size:.875rem}
ul.plain{list-style:none;padding:0;margin:0;background:var(--card);border:1px solid var(--border);border-radius:12px}
ul.plain li{padding:8px 12px;border-bottom:1px solid var(--border)}ul.plain li:last-child{border-bottom:0}
.tabs{display:flex;gap:4px;border-bottom:2px solid var(--border);margin:0 0 16px}
.tabs button{font:inherit;font-weight:600;min-height:44px;padding:0 18px;background:none;color:var(--muted);border:0;
border-bottom:3px solid transparent;margin-bottom:-2px;cursor:pointer}
.tabs button[aria-selected=true]{color:var(--link);border-bottom-color:var(--link)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media (max-width:640px){
.wrap{overflow:visible;background:none;border:0}
.builds,.builds thead,.builds tbody,.builds tr,.builds td{display:block}
.builds thead tr{display:flex;flex-wrap:wrap;gap:6px}
.builds thead th{padding:0 10px;border:0;border-radius:999px}.builds thead th.nosort{display:none}
.builds tbody{background:var(--card);border:1px solid var(--border);border-radius:12px;margin:12px 0;overflow:hidden}
.builds tr.main td{display:flex;justify-content:space-between;gap:12px;padding:6px 12px;border:0;text-align:right}
.builds tr.main td::before{content:attr(data-label);color:var(--muted);font-weight:600;text-align:left}
.builds tr.main td.t{display:block;text-align:left}.builds tr.main td.t::before{display:block}
.builds tr.main td.x::before{content:none}.detail .scroll{overflow-x:auto}}
"""

JS = """
(function(){
var t=document.getElementById('builds');if(!t)return;
var groups=[].slice.call(t.tBodies),ths=[].slice.call(t.tHead.rows[0].cells);
function key(g,i,num){var c=g.rows[0].cells[i];if(!num)return c.textContent.trim().toLowerCase();
var v=c.getAttribute('data-v');return v===null||v===''?null:parseFloat(v);}
ths.forEach(function(th,i){var b=th.querySelector('button');if(!b)return;
b.addEventListener('click',function(){
var asc=th.getAttribute('aria-sort')!=='ascending',num=th.getAttribute('data-type')==='num';
ths.forEach(function(o){o.removeAttribute('aria-sort');});th.setAttribute('aria-sort',asc?'ascending':'descending');
groups.sort(function(a,b){var x=key(a,i,num),y=key(b,i,num);
if(x===null||y===null)return x===y?0:x===null?1:-1;
return (num?x-y:x.localeCompare(y))*(asc?1:-1);});
groups.forEach(function(g){t.appendChild(g);});});});
t.addEventListener('click',function(e){var b=e.target.closest('button.more');if(!b)return;
var open=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',open);
document.getElementById(b.getAttribute('aria-controls')).hidden=!open;});
var q=document.getElementById('q'),d=document.getElementById('deals'),out=document.getElementById('shown');
function filter(){var s=q.value.trim().toLowerCase(),n=0;groups.forEach(function(g){
var ok=(!d.checked||g.getAttribute('data-deal')==='1')&&(!s||g.rows[0].textContent.toLowerCase().indexOf(s)>=0);
g.hidden=!ok;if(ok)n++;});out.textContent=n+' of '+groups.length+' builds shown';}
q.addEventListener('input',filter);d.addEventListener('change',filter);filter();
})();
(function(){
var tabs=[].slice.call(document.querySelectorAll('[role=tab]'));if(!tabs.length)return;
function pick(b,focus){tabs.forEach(function(o){var on=o===b;o.setAttribute('aria-selected',on);o.tabIndex=on?0:-1;
document.getElementById(o.getAttribute('aria-controls')).hidden=!on;});if(focus)b.focus();
try{localStorage.setItem('pm-tab',b.id);}catch(e){}document.dispatchEvent(new Event('pm-tab'));}
tabs.forEach(function(b,i){b.addEventListener('click',function(){pick(b);});
b.addEventListener('keydown',function(e){var k=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;
if(k){e.preventDefault();pick(tabs[(i+k+tabs.length)%tabs.length],true);}});});
var saved=null;try{saved=document.getElementById(localStorage.getItem('pm-tab'));}catch(e){}
if(saved&&tabs.indexOf(saved)>=0)pick(saved);
})();
"""


def _e(v):
    return escape("" if v is None else str(v))


def text(v):
    return "" if v is None else ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)


def _peso(v):
    return "—" if v is None else f"₱{v:,.0f}"


def _href(u):
    return escape(u) if urlparse(u or "").scheme in ("http", "https") else None  # blocks javascript:/data: links


def _badge(label, tone):
    return f'<span class="b {tone}">{_e(label)}</span>'


def _td(label, html, v=None, cls=""):
    data = "" if v is None else f' data-v="{v}"'
    return f'<td data-label="{_e(label)}" class="{cls}"{data}>{html}</td>'


def _basis(p):
    if p["basis"] == "median":
        return _badge(f"median·{p['n']}", "plain")
    return _badge(*BASIS.get(p["basis"], (p["basis"], "slate")))


def _sum(parts, k):
    vals = [p.get(k) for p in parts]
    return None if None in vals else sum(vals)  # one unpriced part = no honest total


def _money(parts):
    return "".join(f'<td class="n">{_peso(_sum(parts, k))}</td>' for k in ("low", "p25", "price"))


def _parts(rows, title):
    out = [f'<div class="scroll"><table class="parts"><caption class="sr">Parts for {_e(title)}</caption>'
           '<thead><tr><th scope="col">Slot</th><th scope="col">Model</th><th scope="col">Lowest</th>'
           '<th scope="col">25th pct</th><th scope="col">Median</th><th scope="col">Basis</th></tr></thead><tbody>']
    rows = [(name, parts) for name, parts in rows if parts]
    for name, parts in rows:
        out.append(f'<tr class="sec"><th colspan="6" scope="colgroup">{name}</th></tr>')
        for p in parts:
            out.append(f'<tr><td>{_e(p["slot"])}</td><td>{_e(p["model"] or "—")}</td>{_money([p])}<td>{_basis(p)}</td></tr>')
        out.append(f'<tr class="tot"><th colspan="2" scope="row">{name} total</th>{_money(parts)}<td></td></tr>')
    if len(rows) > 1:
        out.append(f'<tr class="tot grand"><th colspan="2" scope="row">Total with extras</th>'
                   f'{_money([p for _, parts in rows for p in parts])}<td></td></tr>')
    return "".join(out) + "</tbody></table></div>"


def _list(head, items):
    return f"<h3>{head}</h3><ul>{''.join(f'<li>{_e(i)}</li>' for i in items)}</ul>" if items else ""


def _build(i, r):
    s, href, title = r["specs"], _href(r["url"]), _e(r["title"])
    link = f'<a href="{href}" target="_blank" rel="noopener">{title}</a>' if href else title
    flags = ([_badge("deal", "green")] if r["deal"] else []) + [_badge(f, FLAG.get(f, "slate")) for f in r["flags"]]
    unknown = s.get("unknown") or []
    main = "".join([
        f'<td class="x"><button type="button" class="more" aria-expanded="false" aria-controls="d{i}">'
        f'Parts<span class="sr"> for {title}</span></button></td>',
        _td("Deal", _badge("DEAL", "green") if r["deal"] else "", int(r["deal"])),
        _td("% of parts", "—" if r["pct"] is None else f"{r['pct']:.0%}", r["pct"], "n"),
        *(_td(lbl, _peso(r[k]), r[k], "n") for lbl, k in [("Ask", "ask"), ("Parts value", "unit_value"),
                                                          ("Buy-smart", "buy_smart"), ("With extras", "with_extras")]),
        _td("Title", link, cls="t"),
        *(_td(k.upper(), _e(text(s.get(k)))) for k in ("cpu", "gpu", "ram")),
        _td("Flags", "".join(flags)),
        _td("Seen", f"{r['seen_n']}× since {_e(r['since'])}" if r["seen_n"] > 1 else "", r["seen_n"]),
    ])
    detail = (_parts([("Parts", r["parts"]), ("Extras", r["extras"])], r["title"])
              + _list("Notes", r["notes"]) + _list("Unrecognised spec lines", unknown if isinstance(unknown, list) else [unknown]))
    return (f'<tbody class="{"deal" if r["deal"] else ""}" data-deal="{int(r["deal"])}"><tr class="main">{main}</tr>'
            f'<tr class="detail" id="d{i}" hidden><td colspan="{len(COLS) + 1}">{detail}</td></tr></tbody>')


def _link(r):
    href = _href(r["url"])
    return f'<a href="{href}" target="_blank" rel="noopener">{_e(r["title"])}</a>' if href else _e(r["title"])


def _missing(rows):
    """PCs with specs but a part that has no price: what is missing, and which parts would unlock the most PCs."""
    if not rows:
        return ""
    need = Counter(m.split(":")[0] for r in rows for m in r.get("missing") or [] if "not in description" not in m)
    top = ", ".join(f"{_e(m)} ({n})" for m, n in need.most_common(8))
    body = "".join(f'<tr><td class="n">{_peso(r["ask"])}</td><td>{_link(r)}</td><td>{_e("; ".join(r.get("missing") or []))}</td>'
                   f'<td>{_e(" · ".join(text(r["specs"].get(k)) for k in ("cpu", "gpu", "ram", "ssd") if r["specs"].get(k)))}</td></tr>'
                   for r in sorted(rows, key=lambda r: r["ask"]))
    return (f'<details class="grp" open><summary><h2>Missing a price ({len(rows)})</h2></summary>'
            + (f'<p class="sub">Most needed: {top}. The next run searches for these; or add a price to manual_prices.csv.</p>' if top else "")
            + '<div class="mini-wrap"><table class="mini"><caption class="sr">PCs missing a part price</caption><thead><tr>'
            '<th scope="col">Ask</th><th scope="col">Title</th><th scope="col">Missing</th><th scope="col">Found</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div></details>')


def _nospecs(rows):
    if not rows:
        return ""
    items = "".join(f'<li>{_peso(r["ask"])} · {_link(r)}</li>' for r in sorted(rows, key=lambda r: r["ask"]))
    return (f'<details class="grp"><summary><h2>No specs listed ({len(rows)})</h2></summary>'
            '<p class="sub">No CPU or GPU in the title or description ("DM for specs", specs in photos, or not a PC).</p>'
            f'<ul class="plain">{items}</ul></details>')


def write(rows, path, trends=None):
    all_rows = rows
    rows = [r for r in all_rows if r["unit_value"] is not None]
    nospecs = [r for r in all_rows if r["unit_value"] is None and not (r["specs"].get("cpu") or r["specs"].get("gpu"))]
    missing = [r for r in all_rows if r["unit_value"] is None and r not in nospecs]
    valued = [r["pct"] for r in rows]
    chips = (f'<li><strong>{len(rows)}</strong> valued</li>'
             f'<li><strong>{sum(r["deal"] for r in rows)}</strong> deals (ask &le; 90% of parts)</li>'
             f'<li>best <strong>{f"{min(valued):.0%}" if valued else "—"}</strong> of parts value</li>'
             f'<li><strong>{len(missing)}</strong> missing a price</li><li><strong>{len(nospecs)}</strong> without specs</li>')
    if rows:
        head = "".join(f'<th scope="col" data-type="{t}"><button type="button">{n}</button></th>' for n, t in COLS)
        body = ('<div class="tools"><label for="q">Search</label><input id="q" type="search" placeholder="title, CPU, GPU…">'
                '<label><input id="deals" type="checkbox"> Deals only</label><span id="shown" aria-live="polite"></span></div>'
                '<div class="wrap"><table class="builds" id="builds"><caption class="sr">Built PCs vs sum of part prices</caption>'
                f'<thead><tr><th scope="col" class="nosort"><span class="sr">Details</span></th>{head}</tr></thead>'
                + "".join(_build(i, r) for i, r in enumerate(rows)) + "</table></div>")
    else:
        body = '<p class="empty">No valued builds yet — run with builds.txt searches.</p>'
    pc = f'<ul class="chips">{chips}</ul>{body}{_missing(missing)}{_nospecs(nospecs)}'
    if trends is not None:  # two tabs; trends = trends_html.section(...)
        pc = ('<div class="tabs" role="tablist" aria-label="Report">'
              '<button type="button" role="tab" id="tab-pc" aria-controls="p-pc" aria-selected="true">PC vs Parts</button>'
              '<button type="button" role="tab" id="tab-tr" aria-controls="p-tr" aria-selected="false" tabindex="-1">Price trends</button></div>'
              f'<section id="p-pc" role="tabpanel" aria-labelledby="tab-pc">{pc}</section>'
              f'<section id="p-tr" role="tabpanel" aria-labelledby="tab-tr" hidden>{trends}</section>')
    name = "PC vs Parts" if trends is None else "PC Price Tracker"
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}</title>'
            f'<style>{CSS}</style></head><body><main><h1>{name}</h1>'
            f'<p class="sub">Generated {datetime.now():%Y-%m-%d %H:%M} · asking prices, not sold prices</p>'
            f'{pc}</main><script>{JS}</script></body></html>')
    Path(path).write_text(page, encoding="utf-8")
    return path
