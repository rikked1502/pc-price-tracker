"""Price trends tab of the report page: the Masterlist sheet as a table (same columns and green/amber tints as the Excel);
each model's Chart button opens its median asking price and middle half (25th-75th pct) by week, month or year."""
import json
from datetime import datetime, timedelta

import pandas as pd

import config
import price
from report_html import _e, _href, _peso

CSS = """
:root{--line:#1E40AF}@media (prefers-color-scheme:dark){:root{--line:#93C5FD}}
.seg{display:inline-flex;border:1px solid var(--muted);border-radius:8px;overflow:hidden}
.seg button,.cats button{font:inherit;min-height:44px;padding:0 14px;background:var(--card);color:var(--text);border:0;cursor:pointer}
.seg button+button{border-left:1px solid var(--muted)}
.seg button[aria-pressed=true],.cats button[aria-pressed=true]{background:var(--head);color:var(--on-head);font-weight:600}
.cats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}.cats button{border:1px solid var(--border);border-radius:999px;min-height:36px}
.ml thead th{background:var(--head);color:var(--on-head);white-space:nowrap}
.ml th button{font:inherit;font-weight:600;color:inherit;background:none;border:0;padding:4px 0;cursor:pointer;min-height:36px}
.ml td.lo{background:var(--green-bg);color:var(--green);font-weight:700}.ml td.hi{background:var(--amber-bg);color:var(--amber);font-weight:700}
.ml td.lo a,.ml td.hi a{color:inherit}
.chart{position:sticky;left:16px;max-width:calc(100vw - 66px);padding:4px 0}  /* stays on screen while the table scrolls sideways */
.chart svg{display:block;overflow:visible}.chart svg:focus{outline:none}.chart svg:focus-visible{outline:3px solid var(--ring)}
.grid{stroke:var(--border);stroke-width:1}.axis{fill:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.band{fill:var(--line);opacity:.16}.med{fill:none;stroke:var(--line);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{fill:var(--line);stroke:var(--card);stroke-width:1.5}.dot.thin{fill:var(--card);stroke:var(--line);stroke-width:2}
.cross{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3}
.tip{position:absolute;pointer-events:none;background:var(--card);color:var(--text);border:1px solid var(--border);
border-radius:8px;padding:8px 10px;font-size:.875rem;line-height:1.4;box-shadow:0 4px 12px rgba(0,0,0,.15);white-space:nowrap}
.tip strong{font-variant-numeric:tabular-nums}.tip .m{color:var(--muted)}
.key{display:flex;flex-wrap:wrap;gap:16px;color:var(--muted);font-size:.875rem;margin:4px 0 8px}
.key span{display:inline-flex;align-items:center;gap:6px}.key i{display:inline-block;width:18px;height:10px}
.key .k-band{background:var(--line);opacity:.25}.key .k-med{height:2px;background:var(--line)}
.key .k-thin{width:10px;height:10px;border:2px solid var(--line);border-radius:50%}
"""

JS = """
(function(){
var t=document.getElementById('ml');if(!t)return;
var D=JSON.parse(document.getElementById('tdata').textContent),groups=[].slice.call(t.tBodies),
ths=[].slice.call(t.tHead.rows[0].cells),NS='http://www.w3.org/2000/svg',cat='',per='W',
UNIT={W:'week',M:'month',Y:'year'},segs=[].slice.call(document.querySelectorAll('#per button'));
try{per=localStorage.getItem('pm-per')||'W';}catch(e){}
function peso(v){return '\\u20B1'+Math.round(v).toLocaleString('en-US');}
function lab(s,long){var d=new Date(s+'T00:00:00');if(per==='Y')return String(d.getFullYear());
if(per==='M')return d.toLocaleDateString('en-US',{month:'short',year:'numeric'});
return d.toLocaleDateString('en-US',long?{month:'short',day:'numeric',year:'numeric'}:{month:'short',day:'numeric'});}
function el(n,a,p){var e=document.createElementNS(NS,n);for(var k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e;}
function ticks(lo,hi){var raw=(hi-lo||hi||1)/4,step=Math.pow(10,Math.floor(Math.log10(raw))),f=raw/step;
step*=f>=7.5?10:f>=3.5?5:f>=1.5?2:1;var t=[];for(var v=Math.floor(lo/step)*step;v<hi+step;v+=step)t.push(v);return t;}
function draw(box){
var ws=D.s[box.getAttribute('data-m')][per],W=Math.max(box.clientWidth,280),H=Math.round(Math.min(340,Math.max(220,W*.38))),
L=72,R=24,T=12,B=30,iw=W-L-R,ih=H-T-B,pts=[],at=-1,a=ws[0],z=ws[ws.length-1],
low=ws.reduce(function(p,w){return w[1]<p[1]?w:p;}),ch=(z[1]-a[1])/a[1];
box.innerHTML='<ul class="chips">'+(ws.length>1?'<li>latest '+UNIT[per]+' <strong>'+peso(z[1])+'</strong></li><li><strong>'+
(ch>0?'+':ch<0?'\\u2212':'')+Math.abs(ch*100).toFixed(0)+'%</strong> since '+lab(a[0],1)+'</li><li>cheapest '+UNIT[per]+
' <strong>'+peso(low[1])+'</strong> ('+lab(low[0])+')</li>':'<li>only one '+UNIT[per]+' of data so far: <strong>'+peso(a[1])+'</strong></li>')+
'</ul><div class="key"><span><i class="k-med"></i>median</span><span><i class="k-band"></i>middle half of prices</span>'+
'<span><i class="k-thin"></i>fewer than '+D.thin+' listings that '+UNIT[per]+'</span></div>';
var svg=el('svg',{width:W,height:H,viewBox:'0 0 '+W+' '+H,tabindex:0,role:'img',
'aria-label':'Median asking price by '+UNIT[per]+', '+ws.length+' points. Arrow keys step through them.'},box);
var t0=Date.parse(a[0]),t1=Date.parse(z[0]),lo=Infinity,hi=-Infinity;
ws.forEach(function(w){lo=Math.min(lo,w[2]);hi=Math.max(hi,w[3]);});
var yt=ticks(lo,hi),y0=yt[0],y1=yt[yt.length-1];
function x(s){return L+(t1===t0?iw/2:(Date.parse(s)-t0)/(t1-t0)*iw);}
function y(v){return T+ih-(v-y0)/(y1-y0||1)*ih;}
yt.forEach(function(v){el('line',{class:'grid',x1:L,x2:L+iw,y1:y(v),y2:y(v)},svg);
el('text',{class:'axis',x:L-8,y:y(v)+4,'text-anchor':'end'},svg).textContent=peso(v);});
var every=Math.max(1,Math.ceil(ws.length/Math.max(1,Math.floor(iw/80))));
ws.forEach(function(w,i){if(i%every)return;el('text',{class:'axis',x:x(w[0]),y:H-8,'text-anchor':'middle'},svg).textContent=lab(w[0]);});
var top=ws.map(function(w){return x(w[0])+','+y(w[3]);}),bot=ws.map(function(w){return x(w[0])+','+y(w[2]);}).reverse();
if(ws.length>1){el('path',{class:'band',d:'M'+top.join('L')+'L'+bot.join('L')+'Z'},svg);
el('path',{class:'med',d:'M'+ws.map(function(w){return x(w[0])+','+y(w[1]);}).join('L')},svg);}
var cross=el('line',{class:'cross',y1:T,y2:T+ih,visibility:'hidden'},svg);
ws.forEach(function(w){var p={x:x(w[0]),y:y(w[1]),w:w};pts.push(p);
el('circle',{class:'dot'+(w[4]<D.thin?' thin':''),cx:p.x,cy:p.y,r:5},svg);});
var hit=el('rect',{x:L,y:T,width:iw,height:ih,fill:'transparent'},svg),tip=document.createElement('div');
tip.className='tip';tip.hidden=true;box.appendChild(tip);
function show(i){if(i<0){tip.hidden=true;cross.setAttribute('visibility','hidden');at=-1;return;}
at=i;var p=pts[i],w=p.w;cross.setAttribute('x1',p.x);cross.setAttribute('x2',p.x);cross.setAttribute('visibility','visible');
tip.innerHTML='<div class="m">'+(per==='W'?'Week of ':'')+lab(w[0],1)+'</div><div>Median <strong>'+peso(w[1])+'</strong></div>'+
'<div class="m">Middle half '+peso(w[2])+' \\u2013 '+peso(w[3])+'</div><div class="m">'+w[4]+' listing'+(w[4]==1?'':'s')+'</div>';
tip.hidden=false;var top=svg.getBoundingClientRect().top-box.getBoundingClientRect().top,tw=tip.offsetWidth,left=p.x+12;if(left+tw>W-8)left=p.x-tw-12;
tip.style.left=Math.max(8,left)+'px';tip.style.top=Math.max(0,top+p.y-tip.offsetHeight-12)+'px';}
function near(e){var r=svg.getBoundingClientRect(),mx=(e.clientX-r.left)*W/r.width,b=0;
pts.forEach(function(p,i){if(Math.abs(p.x-mx)<Math.abs(pts[b].x-mx))b=i;});return b;}
hit.addEventListener('pointermove',function(e){show(near(e));});
hit.addEventListener('pointerdown',function(e){show(near(e));});
svg.addEventListener('pointerleave',function(){show(-1);});
svg.addEventListener('blur',function(){show(-1);});
svg.addEventListener('keydown',function(e){var k=e.key;
if(k==='ArrowRight'||k==='ArrowLeft'){e.preventDefault();show(Math.min(pts.length-1,Math.max(0,(at<0?pts.length-1:at)+(k==='ArrowRight'?1:-1))));}
else if(k==='Escape')show(-1);});}
function redraw(){[].forEach.call(t.querySelectorAll('tr.detail:not([hidden]) .chart'),draw);}
function pick(){segs.forEach(function(b){b.setAttribute('aria-pressed',b.getAttribute('data-p')===per);});redraw();}
segs.forEach(function(b){b.addEventListener('click',function(){per=b.getAttribute('data-p');
try{localStorage.setItem('pm-per',per);}catch(e){}pick();});});
pick();
t.addEventListener('click',function(e){var b=e.target.closest('button.more');if(!b)return;
var open=b.getAttribute('aria-expanded')!=='true',d=document.getElementById(b.getAttribute('aria-controls'));
b.setAttribute('aria-expanded',open);d.hidden=!open;if(open)draw(d.querySelector('.chart'));});
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
var q=document.getElementById('mq'),out=document.getElementById('mshown'),cats=[].slice.call(document.querySelectorAll('#cats button'));
function filter(){var s=q.value.trim().toLowerCase(),n=0;groups.forEach(function(g){
var ok=(!cat||g.getAttribute('data-cat')===cat)&&(!s||g.rows[0].textContent.toLowerCase().indexOf(s)>=0);
g.hidden=!ok;if(ok)n++;});out.textContent=n+' of '+groups.length+' models shown';}
cats.forEach(function(b){b.addEventListener('click',function(){cat=b.getAttribute('data-c');
cats.forEach(function(o){o.setAttribute('aria-pressed',o===b);});filter();});});
q.addEventListener('input',filter);filter();
document.addEventListener('pm-tab',redraw);
var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(redraw,150);});
})();
"""

# Masterlist sheet columns, in the Excel's order: (label, ml column, kind); kind lo/hi = the Excel's green/amber tint
COLS = [("Category", "category", "text"), ("Model", "model", "text"), ("Listings", "listings", "num"),
        ("Lowest", "lowest", "lo"), ("Lowest date", "lowest_date", "text"), ("Highest", "highest", "hi"),
        ("Highest date", "highest_date", "text"), ("Recent", "recent", "num"), ("Buy under", "buy_under", "lo"),
        ("Median", "median", "num"), ("Sell at", "sell_at", "hi"), ("Sources", "sources", "text"), ("Last seen", "last_seen", "text")]
LINK = {"lowest": "lowest_link", "highest": "highest_link"}


def _start(ts, per):
    d = datetime.fromtimestamp(ts).date()
    return str(d - timedelta(d.weekday()) if per == "W" else d.replace(day=1) if per == "M" else d.replace(month=1, day=1))


def series(obs):
    """Per model, after the masterlist's outlier trim: {"W"/"M"/"Y": [[period start, median, 25th pct, 75th pct, listings], ...]}
    oldest first; weeks start Monday."""
    out = {}
    for model, g in obs.groupby("model"):
        t = price.trim(g)
        out[model] = {per: [[s, round(x.price.median()), round(x.price.quantile(.25)), round(x.price.quantile(.75)), x.id.nunique()]
                            for s, x in t.groupby(t.seen_at.map(lambda ts: _start(ts, per)))] for per in "WMY"}
    return out


def _cell(r, col, kind):
    v = r[col]
    if kind == "text":
        return f"<td>{'—' if pd.isna(v) else _e(v)}</td>"
    if pd.isna(v):
        return '<td class="n" data-v="">—</td>'
    shown = f"{v:,.0f}" if col in ("listings", "recent") else _peso(v)
    href = _href(r.get(LINK.get(col)))
    if href:
        shown = f'<a href="{href}" target="_blank" rel="noopener">{shown}</a>'
    return f'<td class="n{" " + kind if kind in ("lo", "hi") else ""}" data-v="{v}">{shown}</td>'


def section(ml, obs):
    """The Price trends tab: ml = price.masterlist with dates as dates (as report.write builds it), obs = price.observations.
    Self-contained: carries its own <style> and <script>, so report_html only places it."""
    if ml.empty:
        return '<p class="empty">No priced models yet — run a scrape first.</p>'
    s = series(obs)
    rows = ml.to_dict("records")
    head = "".join(f'<th scope="col" data-type="{"text" if k == "text" else "num"}"><button type="button">{n}</button></th>'
                   for n, _, k in COLS)
    body = "".join(
        f'<tbody data-cat="{_e(r["category"])}"><tr class="main"><td><button type="button" class="more" aria-expanded="false" '
        f'aria-controls="m{i}">Chart<span class="sr"> for {_e(r["model"])}</span></button></td>'
        + "".join(_cell(r, c, k) for _, c, k in COLS)
        + f'</tr><tr class="detail" id="m{i}" hidden><td colspan="{len(COLS) + 1}"><div class="chart" data-m="{i}"></div></td></tr></tbody>'
        for i, r in enumerate(rows))
    cats = "".join(f'<button type="button" data-c="{_e(c)}" aria-pressed="false">{_e(c)}</button>' for c in sorted(ml.category.unique()))
    data = json.dumps({"s": [s[r["model"]] for r in rows], "thin": config.MIN_COUNT}).replace("</", "<\\/")  # can't end the <script>
    return (f'<style>{CSS}</style><div class="tools"><label for="mq">Search</label><input id="mq" type="search" placeholder="model…">'
            '<div class="seg" id="per" role="group" aria-label="Chart period"><button type="button" data-p="W">Weekly</button>'
            '<button type="button" data-p="M">Monthly</button><button type="button" data-p="Y">Yearly</button></div>'
            '<span id="mshown" aria-live="polite"></span></div>'
            f'<div class="cats" id="cats" role="group" aria-label="Category"><button type="button" data-c="" aria-pressed="true">All</button>{cats}</div>'
            '<div class="mini-wrap"><table class="ml" id="ml"><caption class="sr">Masterlist: price range per model</caption>'
            f'<thead><tr><th scope="col"><span class="sr">Chart</span></th>{head}</tr></thead>{body}</table></div>'
            '<p class="sub">Charts count every price seen. Periods before daily scraping began only include listings still up '
            'when first scraped (dated by their post date), so check the listing count on early points.</p>'
            f'<script type="application/json" id="tdata">{data}</script><script>{JS}</script>')
