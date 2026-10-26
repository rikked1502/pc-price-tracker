"""Settings window (opened from the tray): Facebook login, location, sources, keywords, schedule, and the numbers in config.py.
pythonw settings_app.py           open the window
pythonw settings_app.py --setup   first run (setup.bat): turn on Start with Windows, start the tray, open the window"""
import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import config
import fb

HERE = Path(__file__).parent
STARTUP = Path(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "PC Price Tracker.lnk")
TRAY = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(HERE / "tray.ps1")]
SOURCES = [("facebook", "Facebook Marketplace"), ("tipidpc", "TipidPC"), ("carousell", "Carousell")]
# Advanced tab: key, label, lowest allowed, highest allowed
NUMBERS = [("min_price", "Minimum price (₱) — skips placeholder prices like ₱1", 0, 1_000_000),
           ("build_min_price", "PC build searches: lowest price (₱)", 0, 10_000_000),
           ("build_max_price", "PC build searches: highest price (₱)", 0, 10_000_000),
           ("scrolls", "Facebook: scrolls per search", 1, 50),
           ("tipidpc_pages", "TipidPC: result pages per search (40 listings each)", 1, 20),
           ("auto_searches", "Extra searches for parts that left a PC unvalued (0 = off)", 0, 50),
           ("max_age_days", "Prices older than this many days are stale", 1, 3650),
           ("min_count", "Listings a model needs before its price is trusted", 1, 100),
           ("min_profit", "Flips sheet: minimum profit (₱)", 0, 10_000_000)]
FB_RESULT = {"ok": "Facebook finished normally", "login": "Facebook stopped at a login/verification page — log in again",
             "stopped": "the Facebook window was closed before it finished"}


def clean_terms(terms):
    """Trimmed, lower-cased, blank lines and duplicates dropped, order kept."""
    out = []
    for t in terms:
        t = " ".join(t.split()).lower()
        if t and t not in out:
            out.append(t)
    return out


def validate(raw):
    """Form values (strings from the window) -> settings dict for config.save; ValueError names the first bad field."""
    s = {"sources": [k for k, _ in SOURCES if raw["sources"].get(k)], "autorun": bool(raw["autorun"]),
         "parts": clean_terms(raw["parts"]), "builds": clean_terms(raw["builds"])}
    city = raw["city"].strip().lower()
    if not re.fullmatch(r"[a-z0-9-]*", city):  # goes into the Marketplace URL
        raise ValueError("Location: use only letters, numbers and dashes, like the city in facebook.com/marketplace/manila/")
    s["city"] = city
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", raw["run_time"].strip())
    if not m:
        raise ValueError("Daily run time: use 24-hour HH:MM, e.g. 12:00 or 18:30")
    s["run_time"] = f"{int(m[1]):02d}:{m[2]}"
    for key, label, lo, hi in NUMBERS:
        try:
            n = int(raw[key].strip().replace(",", ""))
        except ValueError:
            raise ValueError(f"{label}: enter a whole number") from None
        if not lo <= n <= hi:
            raise ValueError(f"{label}: must be between {lo:,} and {hi:,}")
        s[key] = n
    if s["build_min_price"] > s["build_max_price"]:
        raise ValueError("PC build searches: the lowest price is above the highest price")
    if not s["sources"]:
        raise ValueError("Sources: turn on at least one site")
    return s


def set_startup(on):
    """Create or remove the Startup-folder shortcut that starts the tray at login."""
    if not on:
        STARTUP.unlink(missing_ok=True)
        return
    args = subprocess.list2cmdline(TRAY[1:])
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath = $env:EXE; $s.Arguments = $env:ARGS; "
          "$s.WorkingDirectory = $env:DIR; $s.WindowStyle = 7; $s.Save()")
    env = {**os.environ, "LNK": str(STARTUP), "EXE": TRAY[0], "ARGS": args, "DIR": str(HERE)}  # env, not string-building: paths with quotes stay safe
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)


class Terms(ttk.LabelFrame):
    """A keyword list with Add / Remove / Reset to defaults."""

    def __init__(self, parent, title, key, values, changed):
        super().__init__(parent, text=title, padding=8)
        self.key, self.changed = key, changed
        self.box = tk.Listbox(self, height=12, activestyle="none", selectmode="extended")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.box.yview)
        self.box.configure(yscrollcommand=bar.set)
        self.entry = ttk.Entry(self)
        self.entry.bind("<Return>", lambda e: self.add())
        self.box.grid(row=0, column=0, columnspan=3, sticky="nsew")
        bar.grid(row=0, column=3, sticky="ns")
        self.entry.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(self, text="Add", command=self.add).grid(row=1, column=1, padx=(6, 0), pady=(8, 0))
        ttk.Button(self, text="Remove selected", command=self.remove).grid(row=1, column=2, padx=(6, 0), pady=(8, 0))
        ttk.Button(self, text="Reset to defaults", command=self.reset).grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.set(values)

    def get(self):
        return list(self.box.get(0, "end"))

    def set(self, values):
        self.box.delete(0, "end")
        for v in values:
            self.box.insert("end", v)

    def add(self):
        new = clean_terms([self.entry.get()])
        if new and new[0] not in self.get():
            self.box.insert("end", new[0])
            self.box.see("end")
            self.changed()
        self.entry.delete(0, "end")

    def remove(self):
        for i in reversed(self.box.curselection()):
            self.box.delete(i)
        self.changed()

    def reset(self):
        if messagebox.askyesno("Reset keywords", f"Replace this list with the {len(config.DEFAULTS[self.key])} default keywords?", parent=self):
            self.set(config.DEFAULTS[self.key])
            self.changed()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC Price Tracker — Settings")
        self.minsize(760, 560)
        self.saved = config.load()
        s = self.saved
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        basic, adv = ttk.Frame(tabs, padding=12), ttk.Frame(tabs, padding=12)
        tabs.add(basic, text="Basic")
        tabs.add(adv, text="Advanced")

        login = ttk.LabelFrame(basic, text="Facebook login", padding=8)
        login.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.status, self.last = ttk.Label(login), ttk.Label(login, foreground="gray25")
        self.login_btn = ttk.Button(login, text="Log in to Facebook", command=self.login)
        self.status.grid(row=0, column=0, sticky="w")
        self.login_btn.grid(row=0, column=1, rowspan=2, sticky="e")
        self.last.grid(row=1, column=0, sticky="w")
        ttk.Label(login, text="Opens Edge: log in, finish any verification, then close that window. Your password is never stored here.",
                  foreground="gray25").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        login.columnconfigure(0, weight=1)

        where = ttk.LabelFrame(basic, text="Where and what", padding=8)
        where.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(where, text="Facebook location").grid(row=0, column=0, sticky="w")
        self.city = tk.StringVar(value=s["city"])
        ttk.Entry(where, textvariable=self.city, width=20).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(where, text="Blank = the location set in Marketplace. Or a city from facebook.com/marketplace/manila/ → manila",
                  foreground="gray25").grid(row=0, column=2, sticky="w")
        ttk.Label(where, text="Sources").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.sources = {k: tk.BooleanVar(value=k in s["sources"]) for k, _ in SOURCES}
        row = ttk.Frame(where)
        row.grid(row=1, column=1, columnspan=2, sticky="w", padx=8, pady=(6, 0))
        for k, label in SOURCES:
            ttk.Checkbutton(row, text=label, variable=self.sources[k]).pack(side="left", padx=(0, 12))

        self.parts = Terms(basic, "Part searches (all sites)", "parts", s["parts"], self.touch)
        self.builds = Terms(basic, "Built-PC searches (Facebook only)", "builds", s["builds"], self.touch)
        self.parts.grid(row=2, column=0, sticky="nsew", pady=(10, 0), padx=(0, 6))
        self.builds.grid(row=2, column=1, sticky="nsew", pady=(10, 0), padx=(6, 0))

        when = ttk.LabelFrame(basic, text="Schedule", padding=8)
        when.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(when, text="Daily run time (24h)").pack(side="left")
        self.run_time = tk.StringVar(value=s["run_time"])
        ttk.Entry(when, textvariable=self.run_time, width=7).pack(side="left", padx=(8, 16))
        self.autorun = tk.BooleanVar(value=s["autorun"])
        ttk.Checkbutton(when, text="Run automatically (off = reminder only)", variable=self.autorun).pack(side="left", padx=(0, 16))
        self.startup = tk.BooleanVar(value=STARTUP.exists())
        ttk.Checkbutton(when, text="Start with Windows", variable=self.startup).pack(side="left")
        basic.columnconfigure((0, 1), weight=1)
        basic.rowconfigure(2, weight=1)

        self.nums = {}
        for i, (key, label, lo, hi) in enumerate(NUMBERS):
            ttk.Label(adv, text=label).grid(row=i, column=0, sticky="w", pady=4)
            self.nums[key] = tk.StringVar(value=str(s[key]))
            ttk.Entry(adv, textvariable=self.nums[key], width=12, justify="right").grid(row=i, column=1, sticky="w", padx=8)
            ttk.Label(adv, text=f"default {config.DEFAULTS[key]:,}", foreground="gray25").grid(row=i, column=2, sticky="w")
        ttk.Label(adv, text="Hand-edited files in the app folder: manual_prices.csv (your own part prices), fillins.csv "
                            "(estimates for unnamed parts), aliases.csv (title fixes).", foreground="gray25",
                  wraplength=640).grid(row=len(NUMBERS), column=0, columnspan=3, sticky="w", pady=(12, 0))

        bar = ttk.Frame(self, padding=12)
        bar.pack(fill="x")
        self.note = ttk.Label(bar, text="Changes apply from the next run.", foreground="gray25")
        self.note.pack(side="left")
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.startup_saved = self.startup.get()
        self.refresh()

    def touch(self):
        self.note.configure(text="Unsaved changes.")

    def raw(self):
        return {"city": self.city.get(), "run_time": self.run_time.get(), "autorun": self.autorun.get(),
                "sources": {k: v.get() for k, v in self.sources.items()}, "parts": self.parts.get(), "builds": self.builds.get(),
                **{k: v.get() for k, v in self.nums.items()}}

    def dirty(self):
        try:
            return validate(self.raw()) != self.saved or self.startup.get() != self.startup_saved
        except ValueError:
            return True

    def save(self):
        try:
            s = validate(self.raw())
        except ValueError as e:
            messagebox.showerror("Can't save", str(e), parent=self)
            return False
        config.save(s)
        self.saved = s
        self.parts.set(s["parts"])
        self.builds.set(s["builds"])
        if self.startup.get() != self.startup_saved:
            try:
                set_startup(self.startup.get())
                self.startup_saved = self.startup.get()
            except (OSError, subprocess.CalledProcessError) as e:
                messagebox.showerror("Start with Windows", f"Couldn't change the Startup shortcut: {e}", parent=self)
        self.note.configure(text="Saved. Changes apply from the next run.")
        return True

    def close(self):
        if self.dirty():
            answer = messagebox.askyesnocancel("Unsaved changes", "Save your changes before closing?", parent=self)
            if answer is None or (answer and not self.save()):
                return
        self.destroy()

    def login(self):
        fb.open_login()
        self.after(1500, self.refresh)

    def refresh(self):
        """Every 3s: login status from the profile's cookies; the button waits while a run or the login window has the browser."""
        busy, state = fb.busy(), config.read_state()
        logged = fb.logged_in()
        if busy:
            text = "The browser is in use (a run, or the login window). Close the login window when you're done."
        else:
            text = "✓ Logged in to Facebook" if logged else "✗ Not logged in — Facebook prices will be skipped"
        self.status.configure(text=text)
        self.login_btn.configure(state="disabled" if busy else "normal")
        r = state.get("facebook")
        self.last.configure(text=f"Last run ({state.get('facebook_at', '')}): {FB_RESULT.get(r, r)}" if r else "No run yet.")
        self.after(3000, self.refresh)


def setup():
    """First run: Start with Windows on, tray running (its mutex keeps it to one copy)."""
    set_startup(True)
    subprocess.Popen(TRAY, cwd=HERE, creationflags=subprocess.CREATE_NO_WINDOW)
    print(f"Start with Windows: on ({STARTUP})")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
    App().mainloop()
