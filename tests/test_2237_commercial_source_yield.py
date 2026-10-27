"""Autopilot 2.2.37: commercial source fast-first scheduling and read-only yield."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
from types import SimpleNamespace

from telegram_autopilot.v2.commercial_yield_237 import (
    commercial_source_funnel_24h,
    prioritize_commercial_sources,
)


def _source(id, priority=40):
    return SimpleNamespace(id=id, priority=priority, name=f"Source {id}")


def test_commercial_fast_first_keeps_all_sources_but_moves_useful_ahead():
    original = [_source(1), _source(2), _source(3), _source(4)]
    metrics = [
        {"source_id": 1, "last_added": 0, "last_duration_ms": 60000, "last_outcome": "KNOWN_ONLY"},
        {"source_id": 2, "last_added": 2, "last_duration_ms": 7000, "last_outcome": "OK"},
        {"source_id": 3, "last_added": 0, "last_duration_ms": 3000, "last_outcome": "KNOWN_ONLY"},
    ]
    ordered = prioritize_commercial_sources(original, metrics)
    assert ordered[0].id == 2
    assert ordered[-1].id == 1
    assert sorted(x.id for x in ordered) == sorted(x.id for x in original)
    assert [x.priority for x in original] == [40, 40, 40, 40]


def test_commercial_priority_remains_meaningful_and_unknown_sources_not_dropped():
    src = [_source(1, 12), _source(2, 50), _source(3, 13)]
    metrics = [{"source_id": 2, "last_added": 8, "last_duration_ms": 2000, "last_outcome": "OK"}]
    ranked = prioritize_commercial_sources(src, metrics)
    assert ranked[0].id == 1
    assert {x.id for x in ranked} == {1, 2, 3}


class _FakeStore:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
        CREATE TABLE sources(id INTEGER PRIMARY KEY,channel_id INTEGER,name TEXT,url TEXT,enabled INTEGER,priority INTEGER);
        CREATE TABLE source_health(source_id INTEGER,last_duration_ms INTEGER,last_outcome TEXT,last_added INTEGER,cooldown_until TEXT);
        CREATE TABLE articles(id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,discovered_at TEXT,decision TEXT,stage TEXT,published_at TEXT,blocked_by TEXT,reject_reason TEXT NOT NULL DEFAULT '');
        """)
        self.con.executemany(
            "INSERT INTO sources VALUES(?,?,?,?,?,?)",
            [(10,2,"Fast Company","https://fastcompany.com",1,20),
             (11,2,"Slow Source","https://example.org",1,60),
             (12,1,"Other Channel","https://different.example",1,10)])
        self.con.execute("INSERT INTO source_health VALUES(10,5000,'OK',2,'')")
        self.con.execute("INSERT INTO source_health VALUES(11,60000,'KNOWN_ONLY',0,'')")
        recent = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        old = (datetime.now(timezone.utc) - timedelta(days=3)).astimezone().isoformat(timespec="seconds")
        self.con.executemany(
            "INSERT INTO articles(id,channel_id,source_id,discovered_at,decision,stage,published_at,blocked_by) VALUES(?,?,?,?,?,?,?,?)",
            [(1,2,10,recent,"PUBLISH","PUBLISHED",recent,"NONE"),
             (2,2,10,recent,"REJECT","COLLECTED","","NONE"),
             (3,2,11,recent,"PUBLISH","READY","","MEDIA"),
             (4,2,10,old,"PUBLISH","PUBLISHED",old,"NONE"),
             (5,1,12,recent,"PUBLISH","PUBLISHED",recent,"NONE")])
        self.con.commit()

    @contextmanager
    def connect(self):
        yield self.con


def test_commercial_funnel_counts_discovered_cohort_and_media_blockers_read_only():
    store = _FakeStore()
    result = commercial_source_funnel_24h(store, 2)
    assert result["scope"] == "commercial_source_cohort_24h_read_only"
    assert result["source_count"] == 2
    assert result["collected_24h"] == 3
    assert result["published_24h"] == 1
    assert result["rejected_24h"] == 1
    assert result["media_blocked_24h"] == 1
    assert result["source_cooldowns_not_overridden"] is True
    assert result["editorial_thresholds_unchanged"] is True
    assert [x["source_id"] for x in result["sources"]] == [10, 11]
    assert [x["published_24h"] for x in result["sources"]] == [1, 0]
    assert store.con.execute("SELECT count(*) FROM articles").fetchone()[0] == 5
    assert store.con.execute("SELECT count(*) FROM sources WHERE enabled=1").fetchone()[0] == 3


def test_empty_channel_has_empty_funnel():
    store = _FakeStore()
    data = commercial_source_funnel_24h(store, 42)
    assert data["source_count"] == 0
    assert data["collected_24h"] == 0
