import os
import sqlite3
import time
from pathlib import Path

SCHEMA = """
create table if not exists listings (
    id text primary key, source text, title text, price real, condition text, city text, url text,
    first_seen real, last_seen real, category text, model text, flags text default '', norm_source text
);
create table if not exists prices (id text, price real, seen_at real);
create table if not exists builds (id text primary key, description text, specs text, fetched_at real);  -- id = listings.id; description null = not fetched yet
"""


def connect(path=Path(__file__).with_name(os.environ.get("PM_DB", "data.db"))):  # PM_DB=data_dev.db for test runs
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def save(con, source, lid, title, price, url, city=None, condition=None, posted=None):
    """Upsert a listing and log each new price it shows. A listing's first price is dated by its post date when the site gives one."""
    lid, now = f"{source}:{lid}", time.time()
    old = con.execute("select price from listings where id=?", (lid,)).fetchone()
    if not old or old[0] != price:
        con.execute("insert into prices values (?,?,?)", (lid, price, posted if posted and not old else now))
    con.execute(
        """insert into listings (id, source, title, price, condition, city, url, first_seen, last_seen) values (?,?,?,?,?,?,?,?,?)
           on conflict(id) do update set price=excluded.price, last_seen=excluded.last_seen""",
        (lid, source, title, price, condition, city, url, now, now),
    )
