"""Fill category/model/flags with the regex rules (rules.py + aliases.csv) and builds.specs with specs.py.
Titles and spec lines they can't name go to review.csv."""
import csv
import json
from pathlib import Path

import specs
from rules import classify

REVIEW = Path(__file__).with_name("review.csv")
PARTS = ("GPU", "CPU", "RAM", "SSD", "Motherboard", "Monitor", "PSU")  # a vague PC title isn't a miss: PCs are valued from their description


def _save(con, lid, cat, model, flags):
    con.execute("update listings set category=?, model=?, flags=?, norm_source='rules' where id=?",
                (cat, model, ",".join(sorted(flags)), lid))


def _write_review(rows):
    try:
        with open(REVIEW, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel shows emoji titles correctly
            w = csv.writer(f)
            w.writerow(["kind", "id", "source", "price", "category", "text", "url"])
            w.writerows(sorted(rows, key=lambda r: (r[4], r[5].lower())))
    except PermissionError:
        print(f"  {REVIEW.name} is open in another program, not updated this run")


def _specs(con, review):
    """Re-extract specs for every fetched build. Title + description, so a description FB hid still leaves the title's specs."""
    rows = con.execute("""select b.id, l.source, l.price, l.title, b.description, l.url
                          from builds b join listings l using(id) where b.description is not null""").fetchall()
    for lid, src, price, title, desc, url in rows:
        s = specs.extract(f"{title}\n{desc}")
        con.execute("update builds set specs=? where id=?", (json.dumps(s, ensure_ascii=False), lid))
        review += [("spec", lid, src, price, "PC", line, url) for line in s["unknown"]]
    return len(rows)


def run(con):
    """Re-classify every listing (so a rule or alias fix reaches old rows too), write review.csv, print and return coverage
    as {category: [named, total]}. Phones/consoles/laptops are counted but never sent to review."""
    rows = con.execute("select id, source, title, price, url from listings").fetchall()
    cov, review = {}, []
    for lid, src, title, price, url in rows:
        cat, model, flags = classify(title)
        _save(con, lid, cat, model, flags)
        n = cov.setdefault(cat or "(none)", [0, 0])
        n[0], n[1] = n[0] + bool(model), n[1] + 1
        if not model and (cat is None or cat in PARTS) and "wanted" not in flags:
            review.append(("title", lid, src, price, cat or "", title, url))
    titles, builds = len(review), _specs(con, review)
    con.commit()
    _write_review(review)
    named = sum(n for n, _ in cov.values())
    print(f"  named {named}/{len(rows)} listings ({named / max(len(rows), 1):.0%}); specs for {builds} builds; "
          f"{titles} titles + {len(review) - titles} spec lines to check in {REVIEW.name}")
    for cat, (n, total) in sorted(cov.items(), key=lambda kv: -kv[1][1]):
        print(f"    {cat:<12} {n:>5}/{total:<5} {n / total:5.0%} named")
    return cov
