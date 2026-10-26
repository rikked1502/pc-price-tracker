"""Settings: the defaults below, overridden by settings.json (written by the Settings window; not in git).
Each key is also a module constant: config.MIN_PRICE = settings["min_price"]."""
import json
from pathlib import Path

FILE = Path(__file__).with_name("settings.json")

DEFAULTS = {
    "sources": ["facebook", "tipidpc", "carousell"],
    "city": "",               # Facebook: blank = location set in Marketplace. Or the slug from facebook.com/marketplace/manila/ -> "manila"
    "min_price": 100,         # PHP; skips ₱1/₱2 placeholder listings
    "scrolls": 6,             # Facebook: max scrolls per search term (stops early when results run out)
    "tipidpc_pages": 2,       # TipidPC: result pages per search term (40 listings each)
    "build_min_price": 20000,  # PHP; build searches (Facebook only) use this price range
    "build_max_price": 55000,
    "auto_searches": 10,      # extra part searches per run for the parts that most often left a PC unvalued; 0 = off
    "max_age_days": 90,       # prices older than this are stale: old TipidPC/Carousell posts are skipped, and buy/median/sell use recent listings only
    "min_count": 3,           # listings a model needs before it shows on the Flips sheet
    "min_profit": 1000,       # PHP; Flips sheet threshold (sell_at - buy_under)
    "run_time": "12:00",      # tray: daily run time (24h)
    "autorun": True,          # tray: run at run_time; False = reminder only
    # part searches, used on Facebook, TipidPC and Carousell
    "parts": ["rtx 3060", "rtx 3060 ti", "rtx 3070", "rtx 3080", "rtx 4060", "rtx 4070", "gtx 1660 super", "rx 580", "rx 6600",
              "rx 6700 xt", "ryzen 5600", "ryzen 5700x", "ryzen 5800x3d", "i5 12400f", "i7 12700k", "ddr4 ram", "ddr5 ram",
              "nvme ssd", "b550 motherboard", "b450 motherboard", "b650 motherboard", "a520 motherboard", "h610 motherboard",
              "psu 650w", "psu 750w", "gaming monitor 144hz", "gaming monitor 24", "gaming monitor 27", "iphone 13", "iphone 14",
              "iphone 15", "ps5", "ps4 pro", "nintendo switch", "steam deck", "macbook air m1", "ipad", "airpods pro"],
    # built-PC searches, Facebook only, priced build_min_price..build_max_price; each new PC listing's page is opened once
    "builds": ["gaming pc", "pc set", "system unit", "gaming pc rtx", "pc build ryzen", "complete set pc"],
}


def load(path=FILE):
    """DEFAULTS with settings.json on top; unknown keys are dropped. A broken file falls back to defaults so a scheduled run still runs."""
    try:
        saved = json.loads(path.read_text("utf-8-sig"))  # -sig: the tray (PowerShell 5.1) may write a BOM
    except FileNotFoundError:
        saved = {}
    except (OSError, ValueError) as e:
        print(f"  {path.name} unreadable, using defaults: {e}")
        saved = {}
    return {k: saved.get(k, v) for k, v in DEFAULTS.items()}


def save(settings, path=FILE):
    path.write_text(json.dumps(settings, indent=2), "utf-8")


STATE = Path(__file__).with_name("state.json")  # run history, not settings: tray's last_run/handled, last Facebook result


def read_state():
    try:
        return json.loads(STATE.read_text("utf-8-sig"))
    except (OSError, ValueError):
        return {}


def update_state(**kw):
    STATE.write_text(json.dumps({**read_state(), **kw}, indent=2), "utf-8")


# shortcut: constants are read once at import, so saved changes apply from the next run (each run is a new process)
globals().update({k.upper(): v for k, v in load().items()})
