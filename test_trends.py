"""python -B -m unittest test_trends   (no DB; the sample page goes to %TEMP%)"""
import itertools
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

import price
import report_html
import trends_html

MON, NEXT_MON = datetime(2026, 10, 12, 10).timestamp(), datetime(2026, 10, 19, 10).timestamp()
IDS = itertools.count()


def obs(model, prices, at, category="GPU"):
    return pd.DataFrame({"id": [f"x{next(IDS)}" for _ in prices], "source": "fb", "model": model, "category": category,
                         "price": [float(p) for p in prices], "seen_at": at, "url": "https://x/" + model, "last_seen": time.time()})


class TrendsTest(unittest.TestCase):
    def test_series(self):
        df = pd.concat([obs("RTX 3060", [10000, 11000, 12000], MON + 86400 * 6),  # Sunday: still the 12th's week
                        obs("RTX 3060", [9000, 9500, 100], NEXT_MON)])  # ₱100 "for swap" trimmed
        s = trends_html.series(df)["RTX 3060"]
        self.assertEqual(s["W"], [["2026-10-12", 11000, 10500, 11500, 3], ["2026-10-19", 9250, 9125, 9375, 2]])
        self.assertEqual(s["M"], [["2026-10-01", 10000, 9500, 11000, 5]])
        self.assertEqual(s["Y"], [["2026-01-01", 10000, 9500, 11000, 5]])

    def test_page(self):
        df = pd.concat([obs("<b>RTX</b>", [10000, 11000], MON), obs("RX 580", [3000, 3100, 3200], NEXT_MON, "GPU")])
        ml = price.masterlist(df)
        for c in ["lowest_date", "highest_date", "last_seen"]:
            ml[c] = ml[c].map(lambda t: datetime.fromtimestamp(t).date())
        path = Path(tempfile.gettempdir()) / "pc_vs_parts_trends_test.html"
        html = report_html.write([], path, trends_html.section(ml, df)).read_text("utf-8")
        self.assertIn("&lt;b&gt;RTX&lt;/b&gt;", html)  # model names escaped
        self.assertNotIn("<b>RTX", html.split('id="tdata"')[0])
        self.assertIn('role="tab"', html)
        self.assertIn('class="n lo" data-v="10000.0"><a href="https://x/&lt;b&gt;RTX&lt;/b&gt;"', html)  # Lowest: green + link
        self.assertIn("No priced models yet", trends_html.section(ml.head(0), df))
        print(f"\n  sample HTML: {path}")


if __name__ == "__main__":
    unittest.main()
