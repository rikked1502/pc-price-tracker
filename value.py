"""PC vs Parts: value each built PC (builds.specs) at part medians, fill in unnamed parts, flag deals, merge reposts."""
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path

import config
import price
import rules

FILLINS = Path(__file__).with_name("fillins.csv")
MANUAL = Path(__file__).with_name("manual_prices.csv")
UNIT = ["cpu", "gpu", "ram", "ssd", "board", "psu", "case", "cooler"]


def load_prices(path, key):
    """key -> price from a CSV with a price column; blank and # rows skipped."""
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            k = (r.get(key) or "").strip()
            if not k or k.startswith("#"):
                continue
            try:
                out[k] = float(r["price"])
            except (TypeError, ValueError):
                raise SystemExit(f"{path.name}: bad price for {k!r}: {r['price']!r}")
    return out


def socket(cpu):
    """CPU model name -> socket for the board fill-in; None when unknown."""
    if m := re.match(r"Ryzen (\d)\d{3}", cpu or ""):
        return "AM4" if m[1] in "12345" else "AM5" if m[1] in "789" else None
    if (cpu or "").startswith("Ultra"):
        return "LGA1851"
    if m := re.match(r"i[3579](?:-(\d+)\d{3}|\s(\d+)\w\w Gen)", cpu or ""):  # "i5-12400F" / "i5-7400" / "i5 12th Gen"
        gen = int(m[1] or m[2])
        return "LGA1700" if 12 <= gen <= 14 else "LGA1200" if gen >= 10 else "LGA1151" if gen >= 6 else None
    return None


def part(slot, model, p, p25=None, basis="none", n=None, low=None):
    """low = lowest price seen (masterlist "lowest"); a manual/fill-in price is its own lowest."""
    return {"slot": slot, "model": model, "price": p, "p25": p if p25 is None else p25, "low": p if low is None else low,
            "basis": basis, "n": n}


def lookup(slot, model, ml, manual):
    """Median of recent listings when there are enough, else a manual price, else None."""
    if model in ml.index and ml.at[model, "recent"] >= config.MIN_COUNT:
        r = ml.loc[model]
        return part(slot, model, float(r["median"]), float(r.buy_under), "median", int(r.recent), float(r["lowest"]))
    if model in manual:
        return part(slot, model, manual[model], basis="manual")
    return None


def unit_part(slot, specs, ml, manual, fill):
    model = specs.get(slot)
    if slot == "gpu" and model in rules.VARIANTS:  # size unknown: price the cheapest variant that has a price
        found = [p for m in [f"{model} {s}GB" for s in rules.VARIANTS[model]] + [model] if (p := lookup(slot, m, ml, manual))]
        if found:
            return min(found, key=lambda p: (p["basis"] != "median", p["price"]))
    elif model and slot != "cooler" and (p := lookup(slot, model, ml, manual)):
        return p
    if slot in ("psu", "case"):
        return part(slot, model, fill[slot], basis="estimated")
    if slot == "board":
        s = socket(specs.get("cpu"))
        return part(slot, model, fill[f"board_{s}" if s else "board"], basis="estimated")
    if slot == "cooler":
        return part(slot, model, fill[f"cooler_{model or 'stock'}"], basis="estimated")
    return part(slot, model, None)


def day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def why(p, ml):
    """Plain reason a part has no price: shown on the report, and named ones become the next run's extra searches."""
    if not p["model"]:
        return f"{p['slot'].upper()}: not in description"
    n = int(ml.at[p["model"], "recent"]) if p["model"] in ml.index else 0
    return f"{p['model']}: {n} recent listing{'s' * (n != 1)}, need {config.MIN_COUNT}" if n else f"{p['model']}: no listings yet"


def value(b, ml, manual, fill):
    """One build row: parts, extras, totals, flags."""
    specs = b["specs"]
    parts = [unit_part(s, specs, ml, manual, fill) for s in UNIT if specs.get(s) or s != "gpu"]  # gpu=None is an APU build
    extras = []
    if specs.get("monitor"):
        extras.append(lookup("monitor", specs["monitor"], ml, manual) or part("monitor", specs["monitor"], fill["monitor"], basis="estimated"))
    elif any(c.startswith("set:") for c in specs.get("check") or []):  # "complete set" with an unnamed monitor still includes one
        extras.append(part("monitor", None, fill["monitor"], basis="estimated"))
    extras += [part(p, None, fill[p], basis="estimated") for p in specs.get("peripherals") or []]
    ok = all(p["price"] is not None for p in parts)  # a missing cpu/ram/ssd or unpriced named gpu has price None
    unit = sum(p["price"] for p in parts) if ok else None
    ext = sum(p["price"] for p in extras)
    total = unit + ext if ok else None
    bases = {p["basis"] for p in parts + extras if p["price"]}  # a ₱0 stock cooler isn't worth an "estimated" flag
    notes = list(specs.get("check") or [])
    if not specs.get("gpu") and re.fullmatch(r"Ryzen [1-5]\d{3}(X|XT|X3D)?|.*\dK?F", specs.get("cpu") or ""):
        notes.append("no GPU listed, but the CPU has no graphics")  # valued without a GPU = undervalued
    if re.search(rules.OEM, b["title"].lower()):
        notes.append("OEM system: DIY board/PSU/case fill-ins may overvalue it")
    flags = {"check"} if notes or specs.get("gpu") in rules.VARIANTS else set()
    flags |= bases & {"estimated", "manual"} | (set() if ok else {"can't value"})
    return {"id": b["id"], "url": b["url"], "title": b["title"], "ask": b["ask"], "unit_value": unit,
            "buy_smart": sum(p["p25"] for p in parts) if ok else None, "extras_value": ext, "with_extras": total,
            "pct": b["ask"] / total if total else None, "deal": ok and b["ask"] * 10 <= total * 9,  # integer-ish math: exact at the 90% line
            "flags": sorted(flags), "notes": notes, "parts": parts, "extras": extras,
            "missing": [why(p, ml) for p in parts if p["price"] is None],
            "seen_n": 1, "since": day(b["first_seen"]), "last_seen": day(b["last_seen"]), "specs": specs,
            "_first": b["first_seen"], "_last": b["last_seen"]}


def merge(rows):
    """Reposts: same cpu/gpu/ram/ssd/board and extras, ask within 10% of the cluster's lowest -> one row, the latest listing shown.
    Board + extras in the key: two sellers' identical budget configs (unit vs complete set) aren't one repost."""
    groups, out = {}, []
    for r in sorted(rows, key=lambda r: r["ask"]):
        s = r["specs"]
        if s.get("cpu") is None:
            out.append([r])
            continue
        key = (s["cpu"], s.get("gpu"), s.get("ram"), s.get("ssd"), s.get("board"), bool(r["extras"]))
        clusters = groups.setdefault(key, [])
        if clusters and r["ask"] <= clusters[-1][0]["ask"] * 1.10:
            clusters[-1].append(r)
        else:
            clusters.append([r])
            out.append(clusters[-1])
    merged = []
    for c in out:
        keep = max(c, key=lambda r: r["_last"])
        keep.update(seen_n=len(c), since=day(min(r["_first"] for r in c)))
        merged.append({k: v for k, v in keep.items() if not k.startswith("_")})
    return merged


def value_builds(con):
    """Every build with extracted specs, valued and merged: deals first, then cheapest vs value. Read-only."""
    if not con.execute("select 1 from sqlite_master where name='builds'").fetchone():
        return []
    q = """select b.id, b.specs, l.url, l.title, l.price, l.first_seen, l.last_seen
           from builds b join listings l using(id) where b.specs is not null and l.price is not null"""
    builds = [{"id": i, "specs": json.loads(s), "url": u, "title": t, "ask": p, "first_seen": f, "last_seen": ls}
              for i, s, u, t, p, f, ls in con.execute(q)
              if price.real_price(p) and p >= config.BUILD_MIN_PRICE / 2]  # a ₱123 ask is "pm for price", not a 1% deal
    if not builds:
        return []
    ml = price.masterlist(price.observations(con)).set_index("model")
    manual, fill = load_prices(MANUAL, "model"), load_prices(FILLINS, "item")
    rows = merge([value(b, ml, manual, fill) for b in builds])
    return sorted(rows, key=lambda r: (not r["deal"], r["pct"] is None, r["pct"] or 0))


def wanted(con, n):
    """The n named part models that most often leave a build unvalued (lowercased, ready to use as search terms)."""
    c = Counter(p["model"] for r in value_builds(con) for p in r["parts"] if p["price"] is None and p["model"])
    return [m.lower() for m, _ in c.most_common(n)]
