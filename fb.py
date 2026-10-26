"""Facebook Marketplace search from the result cards' text, so no per-listing page loads for parts.
PC builds get one item-page load each (fetch_details) to read the description."""
import os
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Error as PlaywrightError, sync_playwright

import config
import db

PROFILE = Path(__file__).with_name("profile")  # your saved FB login lives here; don't share this folder
LIGHT = ["--blink-settings=imagesEnabled=false", "--autoplay-policy=user-gesture-required"]  # text is all we need

# Cards up to FB's "Results outside your search" divider; each card's text is price line(s), title, location.
CARDS_JS = r"""() => {
  const outside = /results?\s+outside\s+(of\s+)?your\s+search/i;
  let boundary = null;
  for (const el of document.querySelectorAll('[role="heading"], h1, h2, h3, h4, h5, h6, span')) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join(" ");
    if (outside.test(own)) { boundary = el; break; }
  }
  const out = [];
  for (const a of document.querySelectorAll('a[href*="/marketplace/item/"]')) {
    if (boundary && (boundary.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
    let card = a;
    for (let i = 0; i < 3; i++) if (card.parentElement) card = card.parentElement;
    out.push([a.href, card.innerText || ""]);
  }
  return out;
}"""
# Marketplace only loads more results on a real wheel scroll over the results, not window.scrollBy.
LAST_CARD_JS = """() => {
  const cards = document.querySelectorAll('a[href*="/marketplace/item/"]');
  if (cards.length) cards[cards.length - 1].scrollIntoView({block: "end"});
  return [innerWidth, innerHeight];
}"""

LOGIN_SELECTOR = 'form[action*="login"], input[name="email"], button[name="login"]'
PRICE_LINE = re.compile(r"^((?:php|₱|\$)\s?[\d,.]+\s?k?|free)$", re.I)
# item page: ... "Details" / condition rows, the seller's description, then the seller box
DESC_START = {"details", "description", "seller's description"}
DESC_END = {"seller information", "seller details", "location is approximate", "send seller a message", "message",
            "today's picks", "sponsored"}
DETAIL_ROW = re.compile(r"^(condition|brand|model|colou?r|storage capacity|type)\b", re.I)
CONDITION_VAL = re.compile(r"^(new|used(\s*[-–]\s*[\w ]+)?)$", re.I)
PLACE = re.compile(r"^[\w .'-]+, (ph|philippines)$", re.I)  # "Imus, PH" line above the map
MAIN_TEXT_JS = """() => (document.querySelector('[role="main"]') || document.body).innerText"""


class Blocked(Exception):
    pass


@contextmanager
def browser():
    with sync_playwright() as p:
        # sandbox on = no "--no-sandbox" warning bar; no_viewport = page matches the real window so FB popups fit
        ctx = p.chromium.launch_persistent_context(PROFILE, channel="msedge", headless=False, args=LIGHT,
                                                   chromium_sandbox=True, no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            yield page
        finally:
            ctx.close()


def open_login():
    """Plain Edge, not Playwright, on the scraper's profile: FB's two-step/checkpoint pages stay blank in an automation-flagged browser."""
    edge = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe")
    return subprocess.Popen([str(edge), f"--user-data-dir={PROFILE}", "https://www.facebook.com/marketplace/"])


def login():
    open_login()
    input("Log in to Facebook in the Edge window, CLOSE that window, then press Enter here...")


def busy():
    """True while a browser (a run or the login window) has the profile open: Edge holds profile/lockfile exclusively."""
    try:
        with open(PROFILE / "lockfile", "a"):
            return False
    except PermissionError:
        return True
    except FileNotFoundError:  # no profile yet
        return False


def logged_in():
    """True/False from FB's session cookie in the profile; None while Edge holds the cookie file (login window still open)."""
    src = PROFILE / "Default" / "Network" / "Cookies"
    if not src.exists():
        return False
    with tempfile.TemporaryDirectory() as d:
        try:
            shutil.copy(src, d)
        except PermissionError:
            return None
        con = sqlite3.connect(Path(d, "Cookies"))
        try:
            now = (time.time() + 11644473600) * 1e6  # Chromium time: microseconds since 1601
            row = con.execute("select 1 from cookies where host_key = '.facebook.com' and name = 'c_user' "
                              "and (has_expires = 0 or expires_utc > ?)", (now,)).fetchone()
        finally:
            con.close()
    return row is not None


def _pause(page):
    page.wait_for_timeout(random.uniform(2000, 6000))


def _load(page, url):
    page.goto(url, wait_until="domcontentloaded")
    _pause(page)
    page.keyboard.press("Escape")  # closes FB popups that dim the page and block scrolling
    # logged-out Marketplace still shows listings next to a login form, so check for the form, not just the URL
    if re.search(r"/(checkpoint|two_step_verification|login)", page.url) or page.locator(LOGIN_SELECTOR).count():
        raise Blocked(f"Facebook wants a login/verification ({page.url}). Run `python run.py --login`, and wait before retrying.")


def parse_price(text):
    """'₱25,000' / 'PHP 25000' / '25k' / 'Free' -> float."""
    s = re.sub(r"php|₱|\$|,|\s", "", text, flags=re.I).lower()
    if s == "free":
        return 0.0
    mult = 1000 if s.endswith("k") else 1
    try:
        return float(s.rstrip("k")) * mult
    except ValueError:
        return 0.0


def parse_card(url, text):
    """-> (id, title, price, city) or None. Two price lines = discounted; the first is the current price."""
    lid = re.search(r"/marketplace/item/(\d+)", url)
    lines = [l.strip() for l in text.splitlines() if l.strip() and l.strip().lower() not in ("just listed", "new")]
    prices = []
    while lines and PRICE_LINE.match(lines[0]):
        prices.append(lines.pop(0))
    if not lid or not prices or not lines:
        return None
    if len(lines) == 1:
        return lid[1], lines[0], parse_price(prices[0]), None
    return lid[1], " ".join(lines[:-1]), parse_price(prices[0]), lines[-1]


def parse_description(text):
    """Item page text -> the seller's description, '' when none is found."""
    lines = [l.strip() for l in text.splitlines()]
    low = [l.lower() for l in lines]
    start = next((i + 1 for i, l in enumerate(low) if l in DESC_START), None)
    if start is None:  # no "Details" heading: start after the condition row
        start = next((i + 1 for i, l in enumerate(low) if l.startswith("condition")), None)
    if start is None:
        return ""
    body = []
    for l in lines[start:]:
        if l.lower() in DESC_END:
            break
        body.append(l)
    while body and (not body[0] or DETAIL_ROW.match(body[0]) or CONDITION_VAL.match(body[0])):
        bare_key = DETAIL_ROW.fullmatch(body[0])  # "Brand" alone = its value is on the next line
        del body[:2 if bare_key else 1]
    body = [re.sub(r"\s*(\.\.\.|…)?\s*see more$", "", l, flags=re.I) for l in body if l.lower() not in ("see more", "see less")]
    while body and (not body[-1] or PLACE.match(body[-1])):
        body.pop()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()


def search(page, con, term, min_price=config.MIN_PRICE, max_price=None):
    """-> db ids ("fb:<id>") of the listings this search saved."""
    city = f"{config.CITY}/" if config.CITY else ""  # blank = FB's saved location and radius
    _load(page, f"https://www.facebook.com/marketplace/{city}search/?query={quote(term)}"
                f"&sortBy=creation_time_descend&minPrice={min_price}&exact=false"
                + (f"&maxPrice={max_price}" if max_price else ""))
    found, stalls = {}, 0
    for _ in range(config.SCROLLS):
        before = len(found)
        for url, text in page.evaluate(CARDS_JS):
            if card := parse_card(url, text):
                found.setdefault(card[0], card)
        stalls = stalls + 1 if len(found) == before else 0
        if stalls >= 2:  # nothing new twice in a row: end of results
            break
        w, h = page.evaluate(LAST_CARD_JS)
        page.mouse.move(w // 2, h // 2)
        page.mouse.wheel(0, int(h * 0.9))
        _pause(page)
    for lid, title, price, city in found.values():
        db.save(con, "fb", lid, title, price, f"https://www.facebook.com/marketplace/item/{lid}/", city)
    con.commit()
    print(f"  facebook  {term}: {len(found)} listings")
    return [f"fb:{lid}" for lid in found]


def fetch_details(page, con):
    """Open each build listing whose description isn't fetched yet, once; '' is stored when none is found so it never reloads."""
    todo = con.execute("select b.id, l.url from builds b join listings l on l.id = b.id where b.description is null").fetchall()
    for n, (lid, url) in enumerate(todo, 1):
        _load(page, url)  # also the random 2-6 s pause between listings
        more = page.locator('[role="main"]').get_by_text("See more", exact=True)
        try:
            if more.count():
                more.first.click(timeout=3000)  # FB cuts long descriptions
                page.wait_for_timeout(500)
        except PlaywrightError:
            pass  # truncated text still beats none
        desc = parse_description(page.evaluate(MAIN_TEXT_JS))
        con.execute("update builds set description = ?, fetched_at = ? where id = ?", (desc, time.time(), lid))
        con.commit()  # per listing, so an interrupted run keeps what it fetched
        print(f"  facebook  details {n}/{len(todo)}: {len(desc)} chars")


if __name__ == "__main__":
    assert parse_price("₱25,000") == 25000 and parse_price("PHP 2") == 2 and parse_price("25k") == 25000 and parse_price("Free") == 0
    assert parse_card("https://www.facebook.com/marketplace/item/123/?ref=x", "PHP16,000\nMSI RTX 3070 GAMING X TRIO\nManila, NCR") \
        == ("123", "MSI RTX 3070 GAMING X TRIO", 16000, "Manila, NCR")
    assert parse_card("https://www.facebook.com/marketplace/item/9/", "Just listed\n₱9,000\n₱12,000\nRyzen 5 5600x\nImus") \
        == ("9", "Ryzen 5 5600x", 9000, "Imus")
    assert parse_card("https://www.facebook.com/marketplace/item/9/", "Sponsored") is None
    page1 = """Gaming PC Ryzen 5 5600 RTX 3060 🔥
₱35,000
Listed 2 days ago in Quezon City
Message
Save
Share
Details
Condition
Used - Like new
Ryzen 5 5600 / B550M
RTX 3060 12GB 👌


16GB DDR4 3200, 512GB NVMe
Pwede meetup sa SM North, no lowball po 🙏
Quezon City, PH
Location is approximate
Seller information
Juan Dela Cruz
Today's picks"""
    assert parse_description(page1) == ("Ryzen 5 5600 / B550M\nRTX 3060 12GB 👌\n\n16GB DDR4 3200, 512GB NVMe\n"
                                         "Pwede meetup sa SM North, no lowball po 🙏")
    page2 = """PC set complete
₱28,500
Listed a week ago in Imus, Cavite
Condition: Used - Good
Brand
MSI
i5 12400F + RX 6600 8GB, 750W PSU
Kasama na monitor 24" 144hz, keyboard at mouse... See more
Send seller a message
Message me for details"""
    assert parse_description(page2) == 'i5 12400F + RX 6600 8GB, 750W PSU\nKasama na monitor 24" 144hz, keyboard at mouse'
    page3 = """System unit 💯
₱22,000
Listed 5 hours ago in Manila
Description
Used for 6 months only, legit seller
Message
Seller details"""
    assert parse_description(page3) == "Used for 6 months only, legit seller"
    assert parse_description("This listing isn't available anymore\nToday's picks") == ""
    print("fb parsing ok")
