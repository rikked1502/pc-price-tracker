"""TipidPC and Carousell PH: both serve their search results as plain HTML, so no browser needed."""
import html
import random
import re
import time
import urllib.request
from datetime import datetime
from urllib.parse import quote, quote_plus

import config
import db
from fb import parse_price

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
AGO = {"minute": 60, "hour": 3600, "day": 86400, "week": 7 * 86400, "month": 30 * 86400, "year": 365 * 86400}


def _get(url):
    time.sleep(random.uniform(1.5, 4))  # polite pace
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _find(rx, text):
    m = re.search(rx, text, re.S)
    return html.unescape(m[1]).strip() if m else None


def parse_tipidpc(page):
    """-> [(id, title, price, city, condition, posted_ts)]. Cards: title link, Used/New/Defective tag, price, category, seller (city), mm/dd/yy."""
    out = []
    for card in page.split('<div class="card ')[1:]:
        link = re.search(r'href="/items/(\d+)" class="font-bold">(.*?)</a>', card, re.S)
        price = _find(r'text-tpc-success">(.*?)<', card)
        if not link or not price:
            continue
        date = _find(r"<span>(\d\d/\d\d/\d\d)</span>", card)
        out.append((link[1], html.unescape(link[2]).strip(), parse_price(price), _find(r"<span>&#32;\((.*?)\)</span>", card),
                    _find(r'class="tag[^"]*">(.*?)<', card), date and datetime.strptime(date, "%m/%d/%y").timestamp()))
    return out


def parse_carousell(page, now):
    """-> [(id, title, price, condition, posted_ts, path)]. Cards carry no location; age is relative ('3 days ago')."""
    out = []
    parts = re.split(r'data-testid="listing-card-(\d+)"', page)
    for lid, card in zip(parts[1::2], parts[2::2]):
        title, price, path = _find(r'--max-line:2">(.*?)</p>', card), _find(r'title="(PHP [\d,.]+)"', card), _find(r'href="(/p/[^"?]+)', card)
        if not (title and price and path):
            continue
        age = re.search(r">(\d+) (minute|hour|day|week|month|year)s? ago<", card)
        out.append((lid, title, parse_price(price), _find(r">((?:Brand|Like) new|\w+ used)<", card),
                    age and now - int(age[1]) * AGO[age[2]], path))
    return out


def _keep(price, posted):
    return price >= config.MIN_PRICE and not (posted and posted < time.time() - config.MAX_AGE_DAYS * 86400)


def tipidpc(con, term):
    n = 0
    for p in range(1, config.TIPIDPC_PAGES + 1):
        cards = parse_tipidpc(_get(f"https://tipidpc.com/search?q={quote_plus(term)}&type=items&page={p}"))
        for lid, title, price, city, cond, posted in cards:
            if _keep(price, posted):
                db.save(con, "tipidpc", lid, title, price, f"https://tipidpc.com/items/{lid}", city, cond, posted)
        n += len(cards)
        if len(cards) < 40:  # last page
            break
    con.commit()
    print(f"  tipidpc   {term}: {n} listings")


def carousell(con, term):
    # shortcut: first page only (~45 newest); more pages need the JS "load more" button, add a browser if that's too few
    cards = parse_carousell(_get(f"https://www.carousell.ph/search/{quote(term)}?sort_by=3"), time.time())
    for lid, title, price, cond, posted, path in cards:
        if _keep(price, posted):
            db.save(con, "carousell", lid, title, price, f"https://www.carousell.ph{path}", None, cond, posted)
    con.commit()
    print(f"  carousell {term}: {len(cards)} listings")


if __name__ == "__main__":
    tp = ('<div class="card bg-tpc-surface"><div><a href="/items/45176258" class="font-bold">RTX 3070 &amp; box</a><svg></svg>'
          '<span class="tag ml-2 tag-muted">Used</span></div><div class="text-tpc-text-muted"><span class="font-bold text-tpc-success">₱9,999</span>'
          '<span class="mx-1">·</span><span>Graphics Cards</span><span class="mx-1">·</span>by <a href="/users/rimax" class="text-tpc-text-muted">rimax</a>'
          '<span>&#32;(Manila City, Metro Manila)</span><span class="mx-1">·</span><span>06/13/26</span></div></div>')
    assert parse_tipidpc(tp) == [("45176258", "RTX 3070 & box", 9999, "Manila City, Metro Manila", "Used",
                                  datetime(2026, 6, 13).timestamp())], parse_tipidpc(tp)
    cs = ('<div data-testid="listing-card-1458994224" class="x"><a href="/u/prydain4156/"><p data-testid="listing-card-text-seller-name">prydain</p>'
          '<p class="y" style="color:#57585a">14 days ago</p></a><a class="D_eu" href="/p/asus-rtx-3070-8gb-1458994224/?t-id=1">'
          '<p class="z" style="--max-line:2">ASUS RTX 3070 8gb</p><div><p title="PHP 17,000">PHP 17,000</p></div><p style="color:#57585a">Lightly used</p></a></div>')
    assert parse_carousell(cs, 100 * 86400) == [("1458994224", "ASUS RTX 3070 8gb", 17000, "Lightly used", 86 * 86400,
                                                 "/p/asus-rtx-3070-8gb-1458994224/")], parse_carousell(cs, 100 * 86400)
    print("sites parsing ok")
