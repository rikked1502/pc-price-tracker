"""python run.py              gather prices from every source in config.SOURCES -> classify -> Excel + HTML in output/
python run.py --login      open Edge once to log in to Facebook (session is saved in profile/)
python run.py --no-scrape  rebuild the reports from data.db only
Searches (Settings window or settings.json): parts (every source) and builds (built PCs, Facebook only,
BUILD_MIN/MAX_PRICE; each new PC listing's page is opened once for its description). Each run also searches for
the config.AUTO_SEARCHES part models that most often left a PC unvalued last time.
Run it daily (the tray does); every run adds to data.db, so the masterlist gets more accurate over time."""
import sys
import time
import traceback

import config
import db
import normalize
import report
import rules
import sites
import value


def scrape(con):
    parts, builds = list(config.PARTS), config.BUILDS
    extra = [t for t in value.wanted(con, config.AUTO_SEARCHES) if t not in parts]  # parts blocking a build's valuation
    if extra:
        print("  also searching for missing parts:", ", ".join(extra))
    parts += extra
    for name in ("tipidpc", "carousell"):
        if name in config.SOURCES:
            for term in parts:
                try:
                    getattr(sites, name)(con, term)
                except OSError as e:  # site down / blocked / timeout: skip the term, keep the rest
                    print(f"  {name} {term}: skipped ({e})")
    if "facebook" in config.SOURCES:
        import fb
        try:
            with fb.browser() as page:
                for term in parts:
                    fb.search(page, con, term)
                for term in builds:
                    for lid in fb.search(page, con, term, config.BUILD_MIN_PRICE, config.BUILD_MAX_PRICE):
                        title = con.execute("select title from listings where id = ?", (lid,)).fetchone()[0]
                        if rules.classify(title)[0] in ("PC", None):  # skip laptops/GPUs/phones a "gaming pc" search drags in
                            con.execute("insert or ignore into builds(id) values (?)", (lid,))
                    con.commit()
                fb.fetch_details(page, con)
            result = "ok"
        except (fb.Blocked, fb.PlaywrightError) as e:  # login wall or browser window closed
            print(f"FACEBOOK STOPPED: {str(e)[:300]}")  # report still gets built from what was collected
            result = "login" if isinstance(e, fb.Blocked) else "stopped"
        config.update_state(facebook=result, facebook_at=time.strftime("%Y-%m-%d %H:%M"))  # shown in the Settings window


def main():
    con = db.connect()
    if "--login" in sys.argv:
        import fb
        return fb.login()
    if "--no-scrape" not in sys.argv:
        try:
            scrape(con)
        except KeyboardInterrupt:  # Ctrl+C stops scraping, not the report
            print("SCRAPE INTERRUPTED: building the report from what was collected")
        except Exception:
            traceback.print_exc()
            print("SCRAPE FAILED: building the report from what was collected")
    normalize.run(con)
    print("Report:", report.write(con))


if __name__ == "__main__":
    main()
