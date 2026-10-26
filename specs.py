"""PC listing description -> parts dict. Pure regex; reuses rules.PATTERNS so model names match the price keys."""
import re

from rules import PATTERNS, SYSTEM_BRANDS, VARIANTS

SLOTS = ("cpu", "gpu", "ram", "ssd", "board", "psu", "cooler", "case", "monitor")
SLOT_OF = {"CPU": "cpu", "GPU": "gpu", "RAM": "ram", "SSD": "ssd", "Motherboard": "board", "PSU": "psu", "Monitor": "monitor"}
PERIPHERALS = {"avr": r"\bavr\b", "headset": r"\bhead(?:set|phones?)\b", "keyboard": r"\bkeyboard\b", "mouse": r"\bmouse\b(?!\s?pad)",
               "mousepad": r"\bmouse\s?pad\b", "speaker": r"\bspeakers?\b", "ups": r"\bups\b", "webcam": r"\bweb\s?cam\b"}
COOLERS = [("aio", r"\baio\b|\bliquid\b|water ?cool|\b(?:240|280|360)\s?mm\b"),
           ("air", r"tower cooler|air cooler|\bak\s?[4-6]\d0\b|hyper ?212|\bag\s?[34]00\b|peerless assassin"),
           ("stock", r"\bstock (?:fan|cooler|hsf|heatsink)|\b(?:fan|cooler)\s*[:\-]?\s*stock\b|\bwraith\b")]
# what "no X" / "walang X" removes
NEG = {"cpu": r"cpu|processor|procie", "gpu": r"gpu|vga|video ?card|graphics? card", "ram": r"ram|memory",
       "ssd": r"ssd|nvme|storage", "board": r"mobo|motherboard", "psu": r"psu|power ?supply", "cooler": r"cooler",
       "case": r"case|casing", "monitor": r"monitor", **{p: p for p in PERIPHERALS}}
NO = r"\b(?:no|walang|wala|without|w/o)\s+"
ANY_NEG = "|".join(NEG.values())
JOIN = r"[ \t]*(?:,|and|at|&|/)[ \t]*"  # same line only: "...512gb ssd\nHindi kasama ang monitor" keeps the SSD
NOT_INCL = r"not included|sold separately|(?:hindi|not) kasama"


def _negated(t):
    """Slots/peripherals the text says are missing: "no gpu", "walang kasamang monitor at keyboard",
    "keyboard and mouse not included", "hindi kasama ang monitor" -- but not "no cpu bottleneck"."""
    return {k for k, w in NEG.items() if re.search(
        rf"{NO}(?:kasamang?\s+)?(?:(?:{ANY_NEG})\b{JOIN}){{0,3}}(?:{w})\b(?!\s+(?:bottleneck|issues?|problems?))"
        rf"|(?:{w})\b(?:{JOIN}(?:{ANY_NEG})\b)*[ \t]*\(?[ \t]*(?:{NOT_INCL})|hindi kasama(?:\s+ang)?[^.,\n|]{{0,20}}?\b(?:{w})\b", t)}
# segment separators inside a line: | , " + ", "nvme+hdd", " / ", bullets and emojis
SPLIT = r"\||\s\+\s?|(?<=\w)\+(?=\w)|\s/\s|[•←-⇿■-◿☀-➿⬀-⯿🀀-🫿]"
HDD = r"\b\d+\s?(?:tb|gb)\s?(?:hdd|hard ?d(?:isk|rive))\b"  # dropped so "1tb hdd 256gb ssd" isn't read as SSD 1TB
RAM_SIZE = (r"\b(\d{1,2})\s?(?:gb?)?\s?x\s?(\d{1,2})\b|\b(\d{1,3})\s?(?:gb|gigs?)\b(?=[^,|]{0,20}?\b(?:ram|memory)\b)"
            r"|\b(?:ram|memory)\b[^,|]{0,20}?\b(\d{1,3})\s?(?:gb|gigs?)\b")  # rules' RAM needs a DDR generation; this doesn't
CASE_NAME = r"\W*(?:pc\s*)?(?:case|casing|chassis)\s*[:=\-–]\s*(\w.{0,39})"
CASE = r"(?<!in )\b(?:case|casing|chassis)\b(?! to case)"
SPEC_KW = (r"\b(?:cpu|processor|procie|gpu|vga|video ?card|graphics|ram|memory|ssd|nvme|hdd|storage|mobo|motherboard|board"
           r"|psu|power supply|cooler|fans?|case|casing|monitor)\b|videocard")
KV = r"\W*([a-z][a-z /]{1,18}?)\s*[:=]\s*\S"
NOT_SPEC = (r"price|presyo|location|loc|meet ?ups?|mop|payment|contact|reason.*|condition|status|notes?|warranty|swap|rfs"
            r"|https?|budget|for sale.*|fs")


def _put(out, slot, x):
    old = out[slot]
    # later, more exact text wins: "i5 12th Gen" -> "i5-12400F", "RTX 3060" -> "RTX 3060 12GB"
    if old is None or old.endswith(" Gen") or re.fullmatch(re.escape(old) + r" \d+GB", x):
        out[slot] = x


def extract(text):
    out = {s: None for s in SLOTS} | {"peripherals": [], "check": [], "unknown": []}
    text = text if isinstance(text, str) else ""
    t = text.lower()
    neg = _negated(t)
    perif, ram_size = set(), None
    for line in text.splitlines():
        hit = False
        for seg in re.split(SPLIT, line):
            low, hdd = re.subn(HDD, " ", seg.lower())
            hit = hit or bool(hdd)  # an HDD is known, just not priced
            low = re.sub(r"\bnzxt\s?h\d{3}\w*", "nzxt", low)  # NZXT H510 is a case, not an H510 board
            # in a title "Dell i7 12th gen" means a laptop/PC, but inside a PC's description it is the CPU
            low = re.sub(SYSTEM_BRANDS, " ", low)
            for cat, pats in PATTERNS.items():
                for rx, fmt in pats:
                    if found := [x for m in re.finditer(rx, low) if (x := fmt(m))]:
                        _put(out, SLOT_OF[cat], found[0])
                        hit = True
                        break
            if not ram_size and (m := re.search(RAM_SIZE, low)):
                size = int(m[1]) * int(m[2]) if m[1] else int(m[3] or m[4])
                if size in (4, 8, 16, 32, 64, 128):
                    ram_size, hit = size, True
            if cooler := next((c for c, rx in COOLERS if re.search(rx, low)), None):
                out["cooler"], hit = out["cooler"] or cooler, True
            if m := re.match(CASE_NAME, seg, re.I):
                out["case"], hit = out["case"] if out["case"] not in (None, "yes") else m[1].strip(" .,-"), True
            elif re.search(CASE, low):
                out["case"], hit = out["case"] or "yes", True
            for p, rx in PERIPHERALS.items():
                if re.search(rx, low):
                    perif.add(p)
                    hit = True
            hit = hit or bool(re.search(rf"{NO}|[:\-]\s*(?:none|wala|n/?a)\b", low))  # "no ssd", "GPU: none"
        line = re.sub(r"^\W+", "", line.strip())
        kv = re.match(KV, line.lower())
        # a spec word plus a number ("Videocard 4gb"), or "Key: value"; skips chit-chat like "with box pa yung gpu"
        spec = len(line) <= 100 and re.search(r"\d", line) and re.search(SPEC_KW, line.lower())
        if not hit and line[:80] not in out["unknown"] and (spec or (kv and not re.fullmatch(NOT_SPEC, kv[1].strip()))):
            out["unknown"].append(line[:80])

    if out["ram"] is None and ram_size:
        ddr = re.search(r"(?<!g)ddr\s?([345])", t)
        if not ddr:
            out["check"].append("ram DDR guessed")
        ddr5 = re.match(r"Ryzen [789]\d{3}|Ultra", out["cpu"] or "") or re.match(r"A620|B[68]50|X[68]70", out["board"] or "")
        out["ram"] = f"{ram_size}GB DDR{ddr[1] if ddr else '5' if ddr5 else '4'}"
    unit_only = re.search(r"\bunit only\b", t)
    for s in (neg | ({"monitor"} if unit_only else set())) & set(SLOTS):
        out[s] = None
    out["peripherals"] = [] if unit_only else sorted(perif - neg)
    if out["gpu"] in VARIANTS:
        out["check"].insert(0, f"gpu size unknown: {out['gpu']} ({'/'.join(map(str, VARIANTS[out['gpu']]))}GB)")
    if (out["cpu"] or "").endswith(" Gen"):
        out["check"].append("cpu generation only")
    if re.search(r"\b(?:complete|full)\s?(?:gaming\s+)?(?:pc\s+)?set(?:up)?\b", t) and not out["monitor"] and not unit_only and "monitor" not in neg:
        out["check"].append("set: monitor not itemized")
    return out

