"""Price masterlist: per model the lowest and highest price seen (and when), the typical buy/sell range, and flip margins."""
import re
import time

import pandas as pd

import config

SKIP_CONDITIONS = {"new", "brand new", "defective"}  # site condition tags; the masterlist is second-hand working items
SYSTEM_PRICED = {"CPU", "RAM", "SSD", "Motherboard", "PSU"}  # parts that never cost a whole build's price
# "pm for price" stand-ins sellers type instead of a price (₱123 is the most common in the data). Not 9999: ₱9,999 is real pricing
PLACEHOLDER = re.compile(r"1+|12|123|1234|12345|123456|1234567|9{6,}")


def real_price(p):
    return p is not None and not PLACEHOLDER.fullmatch(f"{p:.0f}")


COLS = ["category", "model", "listings", "lowest", "lowest_date", "lowest_link", "highest", "highest_date", "highest_link",
        "recent", "buy_under", "median", "sell_at", "sources", "last_seen"]


def observations(con):
    """Every price an identified, clean listing has shown (one row per price change)."""
    df = pd.read_sql("""select p.price, p.seen_at, l.id, l.source, l.title, l.condition, l.city, l.url, l.category, l.model,
                               l.flags, l.last_seen
                        from prices p join listings l using(id) where l.model is not null""", con)
    keep = ((df["flags"].fillna("") == "") & (df.price >= config.MIN_PRICE) & df.price.map(real_price)  # df["flags"]: pandas has a .flags
            & ~df.condition.fillna("").str.lower().isin(SKIP_CONDITIONS)
            # a "Ryzen 5 5500" at ₱35k is a whole PC titled by its CPU; with 3 listings the IQR trim can't catch it.
            # shortcut: also drops real parts at ₱20k+ (9800X3D, 64GB DDR5); raise the cap if you value high-end builds
            & ~(df["category"].isin(SYSTEM_PRICED) & (df.price >= config.BUILD_MIN_PRICE)))
    return df[keep]


def trim(g):
    """Outlier cut before picking lowest/highest: first anything under 1/4 or over 4x the model's median ("₱100 for swap",
    typos; works even with 3 listings where IQR can't), then the IQR cut."""
    med = g.price.median()
    g = g[g.price.between(med / 4, med * 4)]
    q1, q3 = g.price.quantile(.25), g.price.quantile(.75)
    return g[g.price.between(q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1))]


def masterlist(obs):
    """lowest/highest = all-time records with their dates; recent/buy_under/median/sell_at = listings still up lately."""
    cutoff = time.time() - config.MAX_AGE_DAYS * 86400
    rows = []
    for model, g in obs.groupby("model"):
        t = trim(g)
        lo, hi = t.loc[t.price.idxmin()], t.loc[t.price.idxmax()]
        cur = t[t.last_seen >= cutoff].sort_values("seen_at").groupby("id").tail(1)  # one vote per listing: its latest price
        rows.append([g.category.mode()[0], model, g.id.nunique(), lo.price, lo.seen_at, lo.url, hi.price, hi.seen_at, hi.url,
                     cur.id.nunique(), cur.price.quantile(.25), cur.price.median(), cur.price.quantile(.75),
                     ", ".join(sorted(g.source.unique())), g.last_seen.max()])
    return pd.DataFrame(rows, columns=COLS).sort_values(["category", "model"])


def flips(ml):
    """Models you can buy at the cheap end and resell at the high end, biggest margin first."""
    f = ml[ml.recent >= config.MIN_COUNT].copy()
    f["margin"] = f.sell_at - f.buy_under
    f["margin_pct"] = f.margin / f.buy_under
    return f[f.margin >= config.MIN_PROFIT].sort_values("margin", ascending=False)


if __name__ == "__main__":
    obs = pd.DataFrame({
        "id": list("abcdefg"), "source": ["fb", "fb", "tipidpc", "carousell", "fb", "fb", "fb"], "model": ["X"] * 6 + ["Y"],
        "category": "GPU", "price": [500.0, 10000, 12000, 14000, 16000, 11000, 3000], "seen_at": [1, 2, 3, 4, 5, 6, 7],
        "url": list("abcdefg"), "last_seen": [time.time()] * 6 + [0],
    })
    ml = masterlist(obs).set_index("model")
    x = ml.loc["X"]
    assert (x.listings, x.lowest, x.lowest_date, x.highest, x.highest_date) == (6, 10000, 2, 16000, 5), x  # ₱500 cut as outlier
    assert x.sources == "carousell, fb, tipidpc" and ml.loc["Y", "lowest"] == ml.loc["Y", "highest"] == 3000
    assert x.recent == 5 and ml.loc["Y", "recent"] == 0 and pd.isna(ml.loc["Y", "median"])  # Y is stale: record kept, no current price
    f = flips(ml.reset_index())
    assert list(f.model) == ["X"] and f.margin.iloc[0] == 14000 - 11000, f
    few = pd.DataFrame({"id": list("abc"), "source": "fb", "model": "Z", "category": "GPU", "price": [100.0, 4500, 5000],
                        "seen_at": [1, 2, 3], "url": list("abc"), "last_seen": [time.time()] * 3})
    z = masterlist(few).iloc[0]
    assert (z["lowest"], z["median"]) == (4500, 4750), z  # "₱100 for swap" dropped even with only 3 listings (IQR keeps it)
    assert [real_price(p) for p in (123, 1, 1234, 123456, 9999, 4500, 0.0)] == [False, False, False, False, True, True, True]
    print("price ok")
