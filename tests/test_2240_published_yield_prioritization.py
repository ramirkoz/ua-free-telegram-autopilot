"""2.2.40: published-vs-collected source yield and hard-source floor evidence.

No source selection, cooldown, publisher policy or editorial threshold is changed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
from types import SimpleNamespace

from telegram_autopilot.v2.commercial_yield_237 import (
    commercial_source_funnel_24h,
    commercial_source_yield_rows_24h,
    prioritize_commercial_sources,
)


def _src(source_id: int, priority: int = 20):
    return SimpleNamespace(id=source_id, name=f"Source {source_id}", priority=priority)


class Store:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
          CREATE TABLE sources (
            id INTEGER PRIMARY KEY, channel_id INTEGER, name TEXT, url TEXT,
            enabled INTEGER, priority INTEGER
          );
          CREATE TABLE source_health (
            source_id INTEGER, last_duration_ms INTEGER, last_outcome TEXT,
            last_added INTEGER, cooldown_until TEXT
          );
          CREATE TABLE articles (
            id INTEGER PRIMARY KEY, channel_id INTEGER, source_id INTEGER,
            discovered_at TEXT, decision TEXT, reject_reason TEXT,
            published_at TEXT, stage TEXT, blocked_by TEXT
          );
          CREATE INDEX idx_article_cohort ON articles(channel_id, discovered_at, source_id);
        """)
        self.con.executemany(
            "INSERT INTO sources VALUES(?,?,?,?,?,?)",
            [
                (11, 2, "Raw Intake Feed", "https://site1.example", 1, 20),
                (12, 2, "Publish Feed", "https://site2.example", 1, 20),
                (13, 2, "Low Volume", "https://site3.example", 1, 50),
                (14, 1, "Other Channel", "https://site4.example", 1, 20),
            ],
        )
        self.con.executemany(
            "INSERT INTO source_health VALUES(?,?,?,?,?)",
            [(11, 8000, "OK", 23, ""), (12, 8000, "OK", 6, ""),
             (13, 8000, "OK", 3, ""), (14, 8000, "OK", 7, "")],
        )
        self.con.commit()

    @contextmanager
    def connect(self):
        yield self.con


def _rows(store: Store):
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    old = (datetime.now(timezone.utc) - timedelta(days=2)).astimezone().isoformat(timespec="seconds")
    values = []
    ident = 1
    def insert(source, channel, count, *, pub=0, short=0, stamp=now):
        nonlocal ident
        for i in range(count):
            published = i < pub
            short_source = pub <= i < pub + short
            reason = "EDITORIAL_MIN_TWO_SENTENCES: source" if short_source else "WEAK_AUDIENCE_FIT"
            values.append((ident, channel, source, stamp,
                           "PUBLISH" if published else "REJECT",
                           "" if published else reason,
                           stamp if published else "",
                           "PUBLISHED" if published else "COLLECTED", "NONE"))
            ident += 1
    insert(11, 2, 23, short=20)
    insert(12, 2, 6, pub=4, short=1)
    insert(13, 2, 3, pub=1)
    insert(14, 1, 25, pub=25)
    insert(11, 2, 3, pub=3, stamp=old)
    store.con.executemany("INSERT INTO articles VALUES(?,?,?,?,?,?,?,?,?)", values)
    store.con.commit()


def test_24h_published_yield_beats_large_100_percent_rejected_raw_feed():
    store = Store()
    _rows(store)
    yield_rows = commercial_source_yield_rows_24h(store, 2)
    with store.connect() as db:
        health_rows = db.execute("SELECT * FROM source_health").fetchall()
    src = [_src(11), _src(12), _src(13, 50)]
    order = prioritize_commercial_sources(src, health_rows, yield_rows)
    assert [x.id for x in order] == [12, 11, 13]
    assert sorted(x.id for x in order) == [11, 12, 13]
    assert all(x.priority in {20, 50} for x in src)
    by_id = {int(y["source_id"]): y for y in yield_rows}
    assert by_id[11]["collected"] == 23 and by_id[11]["published"] == 0
    assert by_id[11]["short_source_rejected"] == 20
    assert by_id[12]["collected"] == 6 and by_id[12]["published"] == 4
    assert 14 not in by_id  # Channel isolation; not a globally boosted feed.


def test_funnel_accounts_for_short_source_rejections_without_loosening_gate():
    store = Store()
    _rows(store)
    report = commercial_source_funnel_24h(store, 2)
    assert report["collected_24h"] == 32
    assert report["published_24h"] == 5
    assert report["short_source_rejected_24h"] == 21
    by_source = {x["source_id"]: x for x in report["sources"]}
    assert by_source[11]["short_source_rejected_24h"] == 20
    assert by_source[12]["short_source_rejected_24h"] == 1
    assert 14 not in by_source
    assert store.con.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 60


def test_unknown_yield_does_not_disable_sources_or_overwhelm_priority():
    originals = [_src(1, 10), _src(2, 40)]
    h = [{"source_id": 2, "last_added": 100, "last_duration_ms": 2500}]
    order = prioritize_commercial_sources(originals, h)
    assert [x.id for x in order] == [1, 2]
    assert len(order) == len(originals)


def test_evidence_does_not_mutate_operator_cooldowns_or_article_rows():
    store = Store()
    _rows(store)
    store.con.execute("UPDATE source_health SET cooldown_until='tomorrow' WHERE source_id=11")
    store.con.commit()
    before = store.con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    commercial_source_yield_rows_24h(store, 2)
    commercial_source_funnel_24h(store, 2)
    after = store.con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    cooling = store.con.execute("SELECT cooldown_until FROM source_health WHERE source_id=11").fetchone()[0]
    assert before == after and cooling == "tomorrow"
