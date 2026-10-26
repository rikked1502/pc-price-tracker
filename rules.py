"""Title -> (category, model, flags). Add a category by adding patterns here; one-off fixes go in aliases.csv."""
import csv
import re
from pathlib import Path


def _name(*parts):
    return " ".join(p for p in parts if p)


def _ryzen(m):
    if m[1].endswith("000") and not m[2]:  # "Ryzen 5 7000 series" is a family, not a CPU you can price
        return None
    return f"Ryzen {m[1]}{(m[2] or '').upper()}"


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# GPUs sold in two memory sizes: the size joins the model name when the text gives it; valuation prices the cheaper one otherwise
VARIANTS = {"RTX 2060": (6, 12), "RTX 3050": (6, 8), "RTX 3060": (8, 12), "RTX 4060 Ti": (8, 16), "RTX 5060 Ti": (8, 16),
            "GTX 1060": (3, 6), "RX 470": (4, 8), "RX 480": (4, 8), "RX 570": (4, 8), "RX 580": (4, 8),
            "RX 6500 XT": (4, 8), "RX 9060 XT": (8, 16)}
VRAM = r"\b(\d{1,2})\s?gb?\b(?![^,|/]{0,8}(?:ram|(?<!g)ddr[345]|ssd|nvme|m\.2|storage))"  # "12GB" / "6GB GDDR6" / "6GB DDR6", not "16GB RAM"
GTX_SUFFIX = {"ti": "Ti", "super": "Super", "s": "Super"}


def _gpu(name, text):
    sizes = [int(v) for v in re.findall(VRAM, text) if int(v) in VARIANTS.get(name, ())]
    return f"{name} {sizes[0]}GB" if sizes else name


def _gtx(m):
    return _gpu(_name("GTX", m[1], GTX_SUFFIX.get(m[2])), m.string)


def _rx(m):
    return _gpu(_name("RX", m[1], m[2] and m[2].upper()), m.string)


RAM_SIZES = {4, 8, 16, 32, 64, 128}  # no 12/24: those are usually GPU memory ("Ventus 2x 12G")
RAM_CTX = r"(?<!g)ddr\s?[345]|\bram\b|\b\d{4}\s?mhz|\bmemory\b"  # (?<!g): GDDR6 is GPU memory


def _ram(size_of):
    """RAM generation from 'DDR4' anywhere in the text, else from the speed (4800MHz+ = DDR5). Unknown generation = no model."""
    def fmt(m):
        ddr, mhz = re.search(r"(?<!g)ddr\s?([345])", m.string), re.search(r"\b(\d{4})\s?mhz", m.string)
        gen = ddr[1] if ddr else mhz and ("5" if int(mhz[1]) >= 4800 else "4" if int(mhz[1]) >= 2133 else "3")
        size = size_of(m)
        return f"{size}GB DDR{gen}" if gen and size in RAM_SIZES else None
    return fmt


def _monitor(m):
    size = re.search(r"\b(\d{2}(?:\.\d)?)\s?-?\s?(?:\"|”|''|inch|in\b)", m.string)
    hz = re.search(r"\b(\d{2,3})\s?hz\b", m.string)
    return _name("Monitor", size and f"{int(float(size[1]) + .5)}in", hz and f"{hz[1]}Hz") if size or hz else None


PSU_CTX = r"psu|\bpower\b|80\s?\+|80 plus|bronze|gold|platinum|modular"


def _psu(watts):
    return f"PSU {watts}W" if 300 <= watts <= 1600 else None


SSD_KW = r"nvme|ssd|m\.?2|evo|nv[1-3]|sn\d{3}|980 pro|990 pro"
SYSTEM_BRANDS = r"\b(dell|hp|lenovo|acer|asus|msi|huawei|lg|apple|hailan)\b"
OEM = r"\b(dell|hp|lenovo|acer|huawei|hailan|thinkcentre)\b"  # sell whole systems, never bare CPUs (MSI/ASUS do sell parts)

# category: [(regex, formatter)], first pattern with a match wins per category; a formatter may return None to reject a match.
# Text is lowercased first. Formatters can read the whole text through m.string.
PATTERNS = {
    "GPU": [
        (r"\b(?:rtx\s?)?(20[6-8]0|30[5-9]0|40[6-9]0|50[5-9]0)\s?(ti|super)?\b",
         lambda m: _gpu(_name("RTX", m[1], m[2] and m[2].title()), m.string)),
        (r"\bgtx\s?(6[5-9]0|7[5-8]0|9[5-8]0|10[5-8]0|16[356]0)\s?(ti|super|s)?\b", _gtx),
        (r"\brx\s?(\d{3,4})\s?(xtx|xt|gre)?\b", _rx),
        (r"\b(6[4-9][05]0|7[6-9]00|90[67]0)\s?(xtx|xt|gre)\b", _rx),  # "9060XT", "XFX 9070 GRE"
        # bare numbers last, so "RX 580 ... better than 1650" stays an RX 580
        (r"\b(16[356]0)\s?(ti|super|s)?\b", _gtx),  # "1660 super" without "gtx"
        (r"\b(10[5-8]0)\s?(ti)\b", _gtx),  # "1080 ti"; a bare 1080 is a screen resolution
        (r"\bgt\s?(710|730|740|1030)\b", lambda m: f"GT {m[1]}"),
        (r"\barc\s?([ab][3-7]\d0)\b", lambda m: f"Arc {m[1].upper()}"),
    ],
    "CPU": [
        (r"\b(?:ryzen\s?[3579]?|r[3579])(?:\s?pro)?[\s-]?(\d{4})(x3d|xt|gt|ge|x|g|f)?\b", _ryzen),
        (r"\b(\d{4})(x3d|x)\b", _ryzen),
        (r"\b(i[3579])[\s/‑-]{0,3}(\d{4,5})(kf|ks|k|f|t)?\b", lambda m: f"{m[1]}-{m[2]}{(m[3] or '').upper()}"),
        (r"\bultra\s?[579]?\s?(2[2-9]\d)(kf|k|f)\b", lambda m: f"Ultra {m[1]}{m[2].upper()}"),  # desktop Core Ultra ("265K")
        (r"\b(g[4-7]\d{3})\b", lambda m: f"Pentium {m[1].upper()}"),
        # "i5 7th gen" alone is a CPU; with a system brand ("Dell i7 9th gen") it's a laptop/PC the rules can't name
        (r"\b(i[3579])[\s/‑-]{0,2}(\d{1,2})(?:st|nd|rd|th)?\s?(?:gen|grn)\b",
         lambda m: None if re.search(SYSTEM_BRANDS, m.string) else f"{m[1]} {_ord(int(m[2]))} Gen"),
    ],
    "RAM": [
        (r"\b(\d{1,2})\s?(?:gb?)?\s?x\s?(\d{1,2})\s?(?:gb?)?\b", _ram(lambda m: int(m[1]) * int(m[2]))),  # 2x8gb, 8gbx2, (16x2)
        (rf"\b(\d{{1,3}})\s?(?:gb?|gigs?)\b(?=[^,|]{{0,20}}?(?:{RAM_CTX}))", _ram(lambda m: int(m[1]))),
        (rf"(?:{RAM_CTX})[^,|]{{0,20}}?\b(\d{{1,3}})\s?(?:gb?|gigs?)\b", _ram(lambda m: int(m[1]))),
    ],
    "SSD": [
        # the size nearest the keyword: not "1tb hdd 256gb ssd" -> 1TB, nor "16gb ddr4 512gb ssd" -> 16GB
        (rf"\b(\d+)\s?(tb|gb)\b(?:(?!ram|hdd|ddr|\d+\s?(?:gb|tb)\b)[^,|]){{0,25}}?\b(?:{SSD_KW})", lambda m: f"SSD {m[1]}{m[2].upper()}"),
        (rf"\b(?:{SSD_KW})\b[^,|]{{0,15}}?\b(\d+)\s?(tb|gb)\b", lambda m: f"SSD {m[1]}{m[2].upper()}"),
        (r"\b(120|128|240|250|256|480|500|512)\s?(?:nvme|ssd)\b", lambda m: f"SSD {m[1]}GB"),  # "512 nvme", no unit
    ],
    "Motherboard": [
        (r"(?<!nzxt )\b(a[3-6]20|b[2-8][56]0|b365|x[3-8]70|h[1-8]10|z[2-8][79]0|h61|h81|b85|h97)(e)?(?!\d)",  # NZXT H510 is a case
         lambda m: f"{m[1].upper()}{(m[2] or '').upper()} Motherboard"),
    ],
    "Monitor": [(r"\bmonit[oe]r\b|\bmoni\b", _monitor)],
    "PSU": [
        (r"\b(\d{3,4})\s?w(?:atts?)?\b", lambda m: _psu(int(m[1])) if re.search(PSU_CTX, m.string) else None),
        (r"\b(?:cx|rmx?|rme|ud|mwe\s?)(\d{3,4})(?:gm|g|x|e|m)?\b|\bp(\d{3})[gbs]\b", lambda m: _psu(int(m[1] or m[2]))),
    ],
}

# Whole systems, priced by their GPU; checked in order. Many laptop titles never say "laptop", only the model line.
SYSTEMS = [
    # Claude names consoles/phones; listed here so "PS5 1TB SSD" isn't read as an SSD
    ("Console", r"\b(ps[345]|playstation|nintendo switch|switch (oled|lite|2)|steam ?deck|xbox|rog ally|legion go)\b"),
    ("Phone", r"\b(iphone|ipad|galaxy (s|z|a|note|tab) ?\d)"),
    ("PC", r"\b(mini ?pc|nuc|thinkcentre|optiplex|sff|desktop)\b|(?<!dual )(?<!single )\btower\b(?! (cooler|fan|heatsink))"),
    ("Laptop", r"\b(laptop|notebook|macbook|chromebook|thinkpad|ideapad|legion|loq|(?<!sapphire )nitro|predator|helios|aspire|travelmate"
               r"|vivobook|zenbook|zephyrus|tuf (gaming )?[af]{1,2}\d+|rog (strix gt?\d*|scar|flow)|strix gt?\d+\w*|tuf dash|victus"
               r"|omen (?:\d+|max)|vector|strix scar|zbook|swift|msi thin|pavilion|elitebook|probook|envy|spectre|latitude|inspiron|vostro|precision|xps|galaxy book|razer blade"
               r"|gf ?63|katana|cyborg|raider|(?<!wraith )stealth|pulse 1[57]|thin 15|modern 1[45]|commercial 1[45]|matebook|expertbook"
               r"|studiobook|yoga|t-book|surface|slim ?[357]|gram|ge\d\d|galaxy book\d?)\b"
               r"|\b\d{4,5}(h[sxk]?|u)\b|\b\d{3}hx\b"),  # laptop CPUs: 4800H, 13700HX, 1335U, 275HX
    ("PC", r"\b(gaming (?:pc|computer|desktop|rig)|pc build|prebuilt|custom pc|full setup|computer|system ?unit|pc ?set"
           r"|full ?set|complete ?set(?:up)?|unit only|rig|build)\b"  # bare "pc" below, but not "PC case" / "PC game" / "PC SN530 NVMe"
           r"|\bpc\b(?!.*\b(case|casing|cd-?rom|dvd|games?|mount|parts?|ssd|nvme|cooler|fans?|psu)\b)"),
]
SPECS = r"\b\d+\s?gb\s?(ram|memory)\b"  # "16GB RAM" in a title = a whole system...
SCREEN = r"\b\d{2}(\.\d)?\s?(\"|”|inch|in\b)"  # ...with a screen size = a laptop
PART_FOR = r"\b(for|pang) (a )?(gaming )?(laptop|pc|desktop|computer)|laptop ram|so-?dimm|\bonly for\b"  # a part, not a system

FLAGS = {
    "parts": r"for parts|broken|not working|doesn.?t work|does not work|no post|no display|\bas[ -]is\b|cracked|\bdead\b"
             r"|needs repair|defect|untested|with issue|for repair|repairable|parts out",
    "wanted": r"\b(wtb|iso|looking for|wanted|buying|bumibili|lf)\b",
    "bundle": r"\b(combo|bundle|bunlde|bulk|job lot|pre[- ]?order|assorted|take ?all|each)\b|\b\d+\s?pcs\b",
    "new": r"(?<!like )\b(brand ?new|bnew|bnib|sealed)\b|brand 🆕",  # the masterlist is second-hand prices
}

ALIASES_CSV = Path(__file__).with_name("aliases.csv")


def _aliases():
    """aliases.csv rows (pattern,category,model): a regex hit on the title sets category/model; blank model = known, not priced."""
    if not ALIASES_CSV.exists():
        return []
    out = []
    with open(ALIASES_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            pat = (r.get("pattern") or "").strip()
            if not pat or pat.startswith("#"):
                continue
            try:
                out.append((re.compile(pat, re.I), (r.get("category") or "").strip() or None, (r.get("model") or "").strip() or None))
            except re.error as e:
                raise SystemExit(f"aliases.csv: bad pattern {pat!r}: {e}")
    return out


ALIASES = _aliases()


def classify(text):
    t = re.sub(r"(?<=\w)\+(?=\w)", " ", text.lower())  # "AMD+RYZEN+7+5700G", "System+unit"
    flags = {f for f, rx in FLAGS.items() if re.search(rx, t)}
    for rx, cat, model in ALIASES:
        if rx.search(t):
            return cat, model, flags
    hits = {}
    for cat, pats in PATTERNS.items():
        for rx, fmt in pats:
            if found := [x for m in re.finditer(rx, t) if (x := fmt(m))]:
                hits[cat] = found[0]
                if len(set(found)) > 1:  # "RTX 2060 also 3060 3070" = a shop list, not one item's price
                    flags.add("bundle")
                break
    gpu = hits.get("GPU")
    if not re.search(PART_FOR, t):
        cat = next((c for c, rx in SYSTEMS if re.search(rx, t)), None)
        if not cat and re.search(SPECS, t):
            cat = "Laptop" if re.search(SCREEN, t) else "PC"
        if cat:
            # shortcut: systems grouped by GPU only (an i3+3060 and i9+3060 compare together); split by CPU if that skews prices
            # no GPU = model None; PCs are valued from their description instead (specs.py)
            return cat, f"{cat} w/ {gpu}" if gpu and cat in ("PC", "Laptop") else None, flags
    if not hits:
        return None, None, flags
    # "LENOVO RYZEN 5 8500GE" is a mini PC (OEMs don't sell bare CPUs); "FS! RYZEN 5 4650G SET" is a PC set
    if "CPU" in hits and (re.search(r"\bset\b", t) or list(hits) == ["CPU"] and re.search(OEM, t)):
        return "PC", f"PC w/ {gpu}" if gpu else None, flags
    # "RYZEN 7 5700X + GIGABYTE DS3H": the board's model wasn't caught. "+ box" / "+ stock cooler" is still one part
    if len(hits) > 1 or re.search(r"\s\+\s(?!(?:box|wifi|stock|cooler|hsf|free\w*|warranty|cash)\b)", t):
        flags.add("bundle")
    cat = next(iter(hits))
    return cat, hits[cat], flags


if __name__ == "__main__":
    cases = [
        ("EVGA RTX 3070 FTW3 Ultra", "GPU", "RTX 3070", set()),
        ("evga 3070 ftw3 ultra", "GPU", "RTX 3070", set()),
        ("RTX 3060 Ti Founders Edition", "GPU", "RTX 3060 Ti", set()),
        ("rtx3070ti", "GPU", "RTX 3070 Ti", set()),
        ("ASUS TUF RX 6700 XT 12GB", "GPU", "RX 6700 XT", set()),
        ("GTX 1660 Super", "GPU","GTX 1660 Super", set()),
        ("Gigabyte 4090 gaming oc", "GPU", "RTX 4090", set()),
        ("AMD Ryzen 5 5600X", "CPU", "Ryzen 5600X", set()),
        ("5800x3d", "CPU", "Ryzen 5800X3D", set()),
        ("Intel Core i7-12700K", "CPU", "i7-12700K", set()),
        ("i5 8400 cpu", "CPU", "i5-8400", set()),
        ("Corsair Vengeance 32GB DDR4 3200", "RAM", "32GB DDR4", set()),
        ("2x8gb ddr4 ram", "RAM", "16GB DDR4", set()),
        ("Samsung 980 Pro 1TB NVMe", "SSD", "SSD 1TB", set()),
        ("Gaming PC i7 RTX 3060 16GB", "PC", "PC w/ RTX 3060", set()),
        ("Gaming laptop RTX 4060", "Laptop", "Laptop w/ RTX 4060", set()),
        ("Custom desktop tower", "PC", None, set()),
        ("RTX 3080 for parts no display", "GPU", "RTX 3080", {"parts"}),
        ("WTB RTX 3080", "GPU", "RTX 3080", {"wanted"}),
        ("Ryzen 5 3600 + RX 580 combo", "GPU", "RX 580", {"bundle"}),
        ("RTX 3070 for gaming pc", "GPU", "RTX 3070", set()),
        ("Monitor 1920x1080 24 inch", "Monitor", "Monitor 24in", set()),
        # real titles from the first live run
        ("Acer Nitro 5 (AN515-58) i5 12th gen RTX 3050", "Laptop", "Laptop w/ RTX 3050", set()),
        ("ASUS TUF Gaming A15 Windows 11 AMD Ryzen 7 4800H 8 GB Ram 4 GB VideoCard NVIDIA RTX 3050", "Laptop", "Laptop w/ RTX 3050", set()),
        ("MSI RAIDER GE78HX 13VG – i7-13700HX | RTX 4070 | 16GB | 2TB", "Laptop", "Laptop w/ RTX 4070", set()),
        ("Razer Blade 16 (2023) – i9 / RTX 4070 / 240Hz", "Laptop", "Laptop w/ RTX 4070", set()),
        ("Dell Latitude 7400 i7 / 16GB / 256GB NVME", "Laptop", None, set()),
        ("Texas Tech mini PC BRAND NEW I7 13th gen Intel UHD Graphics 16gb ram 256gb m.2", "PC", None, {"new"}),
        ("core i7 16gb ram 256gb ssd 14 inch led type c", "Laptop", None, set()),
        ("Core i7 11th Gen / 16 GB RAM /256 GB SSD NVME / Fast Performance", "PC", None, set()),
        ("BEELINK RYZEN 5 6600U 32GB RAM 512 SSD", "Laptop", None, set()),  # mini PC with a laptop CPU; Claude names it
        ("ASUS TUF RTX 3070 OC", "GPU", "RTX 3070", set()),
        ("Kingston 16gb ddr4 3200 laptop ram", "RAM", "16GB DDR4", set()),
        ("Samsung 512gb nvme ssd pang pc", "SSD", "SSD 512GB", set()),
        ("PS5 Slim Disc 1TB SSD", "Console", None, set()),
        ("Steam Deck OLED 512GB", "Console", None, set()),
        ("iPhone 13 Pro 128gb", "Phone", None, set()),
        ("RTX 3070 like brand new", "GPU", "RTX 3070", set()),
        ("RTX 4060 brand new sealed", "GPU", "RTX 4060", {"new"}),
        ("RTX 2060 also 2070 2080 3060 3060ti", "GPU", "RTX 2060", {"bundle"}),
        ("Pre order GPU RX570-RX6700XT GTX1660s-RTX3080", "GPU", "RTX 3080", {"bundle"}),
        # real titles the first rules missed (2026-10-17)
        ("System Unit (Ryzen 5 + 1660 super)", "PC", "PC w/ GTX 1660 Super", set()),
        ("AMD Ryzen 5 5600GT w/ Radeon Graphics 3.60GHz", "CPU", "Ryzen 5600GT", set()),
        ("AMD+RYZEN+7+5700G", "CPU", "Ryzen 5700G", set()),
        ("BUNLDE R7-5700G TRAY TYPE PROCESSOR W ASROCK B550M PRO4 MOTHERBOARD", "CPU", "Ryzen 5700G", {"bundle"}),
        ("[Brand 🆕] Gigabyte B550M-K AM4 DDR4, 4 x RAM slot, 2 x NVMe slot", "Motherboard", "B550 Motherboard", {"new"}),
        ("GIGABYTE B650E AORUS ELITE X AX ICE AM5 DDR5 Motherboard", "Motherboard", "B650E Motherboard", set()),
        ("T-Force Delta White 16gb 3600mhz (8x2) RA", "RAM", "16GB DDR4", set()),
        ("TUF RAM DDR4 3200MHZ 8GBX2 Dual Channel", "RAM", "16GB DDR4", set()),
        ("Corsair CX750 Bronze PSU", "PSU", "PSU 750W", set()),
        ("Gigabyte UD850GM PG5 V2 80 PLUS Gold", "PSU", "PSU 850W", set()),
        ("DeepCool Full Modular PSU 600W", "PSU", "PSU 600W", set()),
        ("AOC 27G2E Gaming Monitor (144hz)", "Monitor", "Monitor 144Hz", set()),
        ("Acer EK251Q P6bi 24.5in FHD IPS 144Hz AMD FreeSync Gaming Monitor", "Monitor", "Monitor 25in 144Hz", set()),
        ("MSI Shadow 2X RTX 5050 8Gb", "GPU", "RTX 5050", set()),
        ("MSI RTX 3060 Ventus 2X 12G OC", "GPU", "RTX 3060 12GB", set()),
        ("Brand New SAPPHIRE NITRO RX580 8GB", "GPU", "RX 580 8GB", {"new"}),
        ("XFX 9070 GRE", "GPU", "RX 9070 GRE", set()),
        ("870 EVO 500GB", "SSD", "SSD 500GB", set()),
        ("Intel Core i5 7th gen processor", "CPU", "i5 7th Gen", set()),
        ("Ultra 7 265K", "CPU", "Ultra 265K", set()),
        ("AVC Dual Tower CPU Cooler", None, None, set()),
        ("Coolmaster Shark X PC Case", None, None, set()),
        ("Asus rog strix g16", "Laptop", None, set()),
        ("i5 10th gen system unit", "PC", None, set()),
        ("BUMIBILI NG RAM DDR4 DDR5", None, None, {"wanted"}),
        ("Sapphire pulse rx 580 2304sp 4gb better than 1650", "GPU", "RX 580 4GB", set()),
        ("Western Digital PC SN530 NVMe M.2 2230 256GB SSD", "SSD", "SSD 256GB", set()),
        ("Dell i7 9th gen", None, None, set()),
        ("Intel Core i5 - 4460", "CPU", "i5-4460", set()),
        ("ROG STRIX G531GV", "Laptop", None, set()),
        ("NZXT H510 case", None, None, set()),
        ("FS! RYZEN 5 4650G SET", "PC", None, set()),
        ("AMD Ryzen 5 7000 series processor", None, None, set()),
        ("RTX 3060 12GB + box", "GPU", "RTX 3060 12GB", set()),
        ("AMD Ryzen 5 PRO 4650G Tray + Stock Cooler", "CPU", "Ryzen 4650G", set()),
        ("Ryzen 5 3600 with Wraith Stealth cooler", "CPU", "Ryzen 3600", set()),
        ("GEFORCE COLORFUL RTX 3050 6GB DDR6", "GPU", "RTX 3050 6GB", set()),
        ("16gb ddr4 512gb ssd", "RAM", "16GB DDR4", {"bundle"}),
        ("RX 580 8gb 16GB 512GB SSD", "GPU", "RX 580 8GB", {"bundle"}),
        ("PALIT RTX 3050 STORMX 6GB GDDR6", "GPU", "RTX 3050 6GB", set()),
        ("Kingston 512 nvme", "SSD", "SSD 512GB", set()),
        ("RYZEN 7 5700X + GIGABYTE DS3H WIFI", "CPU", "Ryzen 5700X", {"bundle"}),
        ("MSI VECTOR 16 (Ultra 7, RTX 5070TI)", "Laptop", "Laptop w/ RTX 5070 Ti", set()),
        ("HP OMEN MAX 16 Ultra 9 275HX RTX 5080", "Laptop", "Laptop w/ RTX 5080", set()),
        ("LENOVO RYZEN 5 8500GE", "PC", None, set()),
        ("HP Intel Core i7 for SALE !!! #GOODforVA", None, None, set()),
        ("1tb hdd 256gb ssd", "SSD", "SSD 256GB", set()),
        ("Power: 650w", "PSU", "PSU 650W", set()),
        ("Lenovo slim 3 i5 10th gen 256g ssd 12g ram", "Laptop", None, set()),
    ]
    for title, cat, model, flags in cases:
        got = classify(title)
        assert got == (cat, model, flags), f"{title!r}: got {got}, want {(cat, model, flags)}"
    print(f"rules ok ({len(cases)} cases)")
