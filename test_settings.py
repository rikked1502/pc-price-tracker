"""python -B -m unittest test_settings   (no window opened; files go to %TEMP%)"""
import tempfile
import unittest
from pathlib import Path

import config
import settings_app as app


def form(**kw):
    """Window values as strings, from the defaults."""
    d = config.DEFAULTS
    return {"city": "", "run_time": "12:00", "autorun": True, "sources": {k: k in d["sources"] for k, _ in app.SOURCES},
            "parts": d["parts"], "builds": d["builds"], **{k: str(d[k]) for k, *_ in app.NUMBERS}, **kw}


class SettingsTest(unittest.TestCase):
    def test_load_save(self):
        path = Path(tempfile.mkdtemp()) / "settings.json"
        self.assertEqual(config.load(path), config.DEFAULTS)  # no file yet
        config.save({**config.DEFAULTS, "city": "manila", "stray": 1}, path)
        s = config.load(path)
        self.assertEqual(s["city"], "manila")
        self.assertNotIn("stray", s)  # unknown keys dropped
        path.write_bytes(b'\xef\xbb\xbf{"min_price": 500}')  # PowerShell's BOM
        self.assertEqual(config.load(path)["min_price"], 500)
        path.write_text("{broken", "utf-8")
        self.assertEqual(config.load(path), config.DEFAULTS)  # a scheduled run still runs

    def test_clean_terms(self):
        self.assertEqual(app.clean_terms(["  RTX  3060 ", "rtx 3060", "", "PS5"]), ["rtx 3060", "ps5"])

    def test_validate(self):
        s = app.validate(form(city=" Manila ", run_time="7:05", min_price="1,000", parts=["RTX 3060", "rtx 3060"]))
        self.assertEqual((s["city"], s["run_time"], s["min_price"], s["parts"]), ("manila", "07:05", 1000, ["rtx 3060"]))
        self.assertEqual(set(s), set(config.DEFAULTS))  # every setting, nothing else
        for bad, msg in [({"city": "manila/../x"}, "Location"), ({"run_time": "25:00"}, "run time"),
                         ({"scrolls": "0"}, "scrolls"), ({"min_price": "abc"}, "whole number"),
                         ({"build_min_price": "60000"}, "above"), ({"sources": {}}, "Sources")]:
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, msg):
                app.validate(form(**bad))


if __name__ == "__main__":
    unittest.main()
