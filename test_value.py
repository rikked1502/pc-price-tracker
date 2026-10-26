import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import db
import value

BUILDS = "create table if not exists builds (id text primary key, description text, specs text, fetched_at real)"
PARTS = {"Ryzen 5600": (8000, 9000, 10000), "RTX 3060 8GB": (10000, 11000, 12000), "RTX 3060 12GB": (13000, 14000, 15000),
         "16GB DDR4": (1500, 2000, 2500), "SSD 512GB": (1000, 1200, 1400), "Monitor 24in 165Hz": (5000, 6000, 7000),
         "RTX 4060": (15000, 17000), "RX 6600": (9000, 10000), "i5-12400F": (6000, 6500)}  # last three: too few listings
FILL = {"psu": 1500, "case": 1200, "cooler_stock": 0, "cooler_air": 800, "cooler_aio": 3000, "board_AM4": 3000,
        "board_AM5": 6000, "board_LGA1700": 4000, "board_LGA1200": 2500, "board_LGA1151": 1500, "board_LGA1851": 7000,
        "board": 2500, "monitor": 3500, "keyboard": 500, "mouse": 300, "headset": 500, "ups": 2000, "avr": 500,
        "speaker": 400, "webcam": 400, "mousepad": 100}
SPECS = {"cpu": "Ryzen 5600", "gpu": "RTX 3060 12GB", "ram": "16GB DDR4", "ssd": "SSD 512GB", "board": None, "psu": None,
         "monitor": "Monitor 24in 165Hz", "cooler": None, "case": None, "peripherals": ["keyboard", "mouse"], "check": [],
         "unknown": []}
# unit: 9000+14000+2000+1200 + board_AM4 3000 + psu 1500 + case 1200 + stock cooler 0; extras: 6000+500+300
UNIT, SMART, EXTRAS = 31900, 8500 + 13500 + 1750 + 1100 + 3000 + 1500 + 1200, 6800


class ValueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Path(tempfile.mkdtemp())
        value.FILLINS, value.MANUAL = d / "fillins.csv", d / "manual.csv"
        value.FILLINS.write_text("item,price,note\n# comment\n\n" + "".join(f"{k},{v},x\n" for k, v in FILL.items()), "utf-8")
        value.MANUAL.write_text("model,price\n# RTX 3060 12GB,1\nRTX 4060,16000\ni5-12400F,7000\n", "utf-8")

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(db.SCHEMA + BUILDS)
        self.now, n = time.time(), 0
        for model, prices in PARTS.items():
            for p in prices:
                n += 1
                self.listing(f"p{n}", model, p)

    def listing(self, lid, model, p, last=None, first=None):
        t = last or self.now
        self.con.execute("insert into listings (id, source, title, price, url, first_seen, last_seen, category, model) "
                         "values (?,?,?,?,?,?,?,?,?)", (lid, "fb", lid, p, "u/" + lid, first or t, t, "PC" if model is None else "X", model))
        self.con.execute("insert into prices values (?,?,?)", (lid, p, t))

    def build(self, lid, ask, last=None, first=None, **kw):
        self.listing(lid, None, ask, last, first)
        self.con.execute("insert into builds values (?,?,?,?)", (lid, "", json.dumps({**SPECS, **kw}), self.now))

    def rows(self):
        return {r["id"]: r for r in value.value_builds(self.con)}

    def test_median_sum_extras_and_deal_boundary(self):
        self.build("deal", 34830)  # exactly 90% of 38700
        r = self.rows()["deal"]
        self.assertEqual((r["unit_value"], r["buy_smart"], r["extras_value"], r["with_extras"]), (UNIT, SMART, EXTRAS, UNIT + EXTRAS))
        self.assertTrue(r["deal"])
        self.assertAlmostEqual(r["pct"], 0.9)
        self.assertEqual(r["flags"], ["estimated"])
        p = {x["slot"]: x for x in r["parts"]}
        self.assertEqual((p["cpu"]["basis"], p["cpu"]["n"], p["cpu"]["p25"], p["cpu"]["low"]), ("median", 3, 8500, 8000))
        self.assertEqual((p["board"]["low"], p["board"]["price"]), (3000, 3000))  # fill-in: its own lowest
        self.assertEqual((p["board"]["basis"], p["board"]["price"], p["board"]["model"]), ("estimated", 3000, None))
        self.assertEqual([(e["slot"], e["price"], e["basis"]) for e in r["extras"]],
                         [("monitor", 6000, "median"), ("keyboard", 500, "estimated"), ("mouse", 300, "estimated")])
        self.assertEqual(set(r), {"id", "url", "title", "ask", "unit_value", "buy_smart", "extras_value", "with_extras", "pct",
                                  "deal", "flags", "notes", "parts", "extras", "missing", "seen_n", "since", "last_seen", "specs"})
        self.assertEqual(r["missing"], [])

    def test_set_with_unnamed_monitor(self):
        self.build("b", 30000, monitor=None, peripherals=[], check=["set: monitor not itemized"])
        r = self.rows()["b"]
        self.assertEqual([(e["slot"], e["price"], e["basis"]) for e in r["extras"]], [("monitor", 3500, "estimated")])
        self.assertEqual(r["flags"], ["check", "estimated"])

    def test_deal_off_by_one(self):
        self.build("b", 34831)
        self.assertFalse(self.rows()["b"]["deal"])

    def test_variant_gpu_cheaper_and_check(self):
        self.build("b", 30000, gpu="RTX 3060", check=["gpu size unknown: RTX 3060 (8/12GB)"])
        r = self.rows()["b"]
        gpu = r["parts"][1]
        self.assertEqual((gpu["model"], gpu["price"], gpu["basis"]), ("RTX 3060 8GB", 11000, "median"))
        self.assertEqual(r["unit_value"], UNIT - 3000)
        self.assertIn("check", r["flags"])
        self.assertEqual(r["notes"], ["gpu size unknown: RTX 3060 (8/12GB)"])

    def test_thin_data_manual_then_cant_value(self):
        self.build("manual", 30000, gpu="RTX 4060")
        self.build("none", 30000, gpu="RX 6600", ram="8GB DDR4")
        self.build("apu", 20000, gpu=None, ram="16GB DDR4", ssd=None, cpu="Ryzen 5600", cooler="air", monitor=None, peripherals=[])
        rows = value.value_builds(self.con)
        by = {r["id"]: r for r in rows}
        m = by["manual"]
        self.assertEqual(m["parts"][1]["basis"], "manual")
        self.assertEqual(m["unit_value"], UNIT - 14000 + 16000)
        self.assertEqual(m["flags"], ["estimated", "manual"])
        for lid in ("none", "apu"):  # RX 6600 thin and not manual; apu has no ssd
            self.assertEqual((by[lid]["unit_value"], by[lid]["with_extras"], by[lid]["pct"], by[lid]["deal"]), (None, None, None, False))
            self.assertIn("can't value", by[lid]["flags"])
        self.assertEqual(rows[-1]["pct"], None)
        self.assertNotIn("gpu", [p["slot"] for p in by["apu"]["parts"]])

    def test_apu_build_values_without_gpu(self):
        self.build("b", 15000, gpu=None, cooler="aio", monitor="Monitor 27in", peripherals=["ups"])
        r = self.rows()["b"]
        self.assertEqual(r["unit_value"], UNIT - 14000 + 3000)
        self.assertEqual([e["price"] for e in r["extras"]], [3500, 2000])  # unlisted monitor -> fill-in
        self.assertEqual((r["notes"], "check" in r["flags"]), (["no GPU listed, but the CPU has no graphics"], True))  # 5600 has no iGPU
        self.build("g", 15000, gpu=None, cpu="Ryzen 5600G", title="Dell Optiplex")
        self.assertEqual(self.rows()["g"]["notes"], [])

    def test_oem_title_flagged(self):
        self.listing("oem", None, 20000)
        self.con.execute("update listings set title='Dell Optiplex 3000 i5-12400' where id='oem'")
        self.con.execute("insert into builds values ('oem', '', ?, 0)", (json.dumps(SPECS),))
        self.assertIn("OEM system", self.rows()["oem"]["notes"][0])

    def test_board_by_socket(self):
        self.build("b", 30000, cpu="i5-12400F")
        p = {x["slot"]: x for x in self.rows()["b"]["parts"]}
        self.assertEqual((p["cpu"]["basis"], p["board"]["price"]), ("manual", 4000))
        cases = {"Ryzen 5600G": "AM4", "Ryzen 2600": "AM4", "Ryzen 7800X3D": "AM5", "Ryzen 8500GE": "AM5", "i5-12400F": "LGA1700",
                 "i5 13th Gen": "LGA1700", "i5-10400": "LGA1200", "i7-11700": "LGA1200", "i5-7400": "LGA1151", "i5 7th Gen": "LGA1151",
                 "Ultra 265K": "LGA1851", "i5-4460": None, "i5 4th Gen": None, None: None}
        self.assertEqual({c: value.socket(c) for c in cases}, cases)

    def test_repost_merge(self):
        day = 86400
        self.build("old", 30000, last=self.now - 5 * day, first=self.now - 20 * day)
        self.build("new", 32000, first=self.now - 3 * day)
        self.build("far", 40000)
        self.build("unit", 31000, monitor=None, peripherals=[])  # same parts, but a unit vs a set: a different listing
        rows = value.value_builds(self.con)
        self.assertEqual(sorted((r["id"], r["seen_n"]) for r in rows), [("far", 1), ("new", 2), ("unit", 1)])
        new = [r for r in rows if r["id"] == "new"][0]
        self.assertEqual((new["url"], new["ask"]), ("u/new", 32000))
        self.assertEqual(new["since"], time.strftime("%Y-%m-%d", time.localtime(self.now - 20 * day)))

    def test_placeholder_ask_skipped(self):
        self.build("pm", 123)
        self.build("cheap", 5000)  # far below any build price: not a real ask
        self.assertEqual(self.rows(), {})

    def test_missing_reasons_and_wanted(self):
        self.build("a", 30000, gpu="GTX 1070 Ti")  # never listed
        self.build("b", 30000, gpu="GTX 1070 Ti", cpu="i5-12400F", ram=None)  # cpu has a manual price; ram not stated
        self.build("c", 30000, gpu="RTX 4060", cpu="Ryzen 7700")  # 2 recent RTX 4060 listings, but a manual price exists
        self.listing("x1", "Ryzen 7700", 9000)
        rows = self.rows()
        self.assertEqual(rows["a"]["missing"], ["GTX 1070 Ti: no listings yet"])
        self.assertEqual(rows["b"]["missing"], ["GTX 1070 Ti: no listings yet", "RAM: not in description"])
        self.assertEqual(rows["c"]["missing"], ["Ryzen 7700: 1 recent listing, need 3"])
        self.assertEqual(value.wanted(self.con, 10), ["gtx 1070 ti", "ryzen 7700"])
        self.assertEqual(value.wanted(self.con, 0), [])

    def test_no_builds_table(self):
        con = sqlite3.connect(":memory:")
        con.executescript(db.SCHEMA)
        self.assertEqual(value.value_builds(con), [])


if __name__ == "__main__":
    unittest.main()
