from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_autopilot import rc80_runtime as rc80


def test_same_source_different_stories_can_not_be_merged_by_ai_topic_match(monkeypatch):
    monkeypatch.setattr(rc80, "_local_duplicate_hit", lambda *_a: None)
    a = {
        "id": 10,
        "source_id": 7,
        "source_name": "The Drum",
        "title": "How Jamie Oliver's midlife crisis became a Life360 microdrama",
        "raw_text": "A branded entertainment story about Jamie Oliver and Life360.",
        "url": "https://example.test/a",
    }
    b = {
        "id": 11,
        "source_id": 7,
        "source_name": "The Drum",
        "title": "Trained marketers warn short-term thinking undermines effectiveness",
        "raw_text": "A separate industry analysis about short-term marketing decisions.",
        "url": "https://example.test/b",
    }
    relation, reason = rc80._guard_relation_rc80(a, b, "DUPLICATE", "AI guessed same event")
    assert relation == "RELATED"
    assert "same source" in reason


def test_dlss_same_topic_different_events_are_related(monkeypatch):
    monkeypatch.setattr(rc80, "_local_duplicate_hit", lambda *_a: None)
    a = {
        "id": 20,
        "source_id": 1,
        "source_name": "Tom's Hardware",
        "title": "DLSS 5 works on AMD RDNA 4 through a mod",
        "raw_text": "RX 9070 XT can run DLSS 5 through DLSS-NR-on-AMD.",
        "url": "https://example.test/dlss-amd",
    }
    b = {
        "id": 21,
        "source_id": 2,
        "source_name": "The Verge",
        "title": "DLSS 5 launches officially in NBA 2K27",
        "raw_text": "NBA 2K27 is the first official DLSS 5 release on RTX 50 GPUs.",
        "url": "https://example.test/dlss-nba",
    }
    relation, reason = rc80._guard_relation_rc80(a, b, "DUPLICATE", "AI matched DLSS 5")
    assert relation == "RELATED"
    assert "blocked merge" in reason


def test_local_high_precision_duplicate_confirmation_keeps_merge(monkeypatch):
    class Hit:
        reason = "same concrete event by strong content overlap"

    monkeypatch.setattr(rc80, "_local_duplicate_hit", lambda *_a: Hit())
    a = {
        "source_id": 1,
        "title": "Nike opens a temporary pawn shop for vintage sneakers",
        "raw_text": "Nike opened a temporary pawn shop where visitors exchange vintage sneakers.",
        "url": "https://a.test/story",
    }
    b = {
        "source_id": 2,
        "title": "Nike turns sneaker shopping into a pawn-shop activation",
        "raw_text": "The Nike activation lets visitors exchange old sneakers in a temporary pawn shop.",
        "url": "https://b.test/story",
    }
    relation, reason = rc80._guard_relation_rc80(a, b, "DUPLICATE", "AI same event")
    assert relation == "DUPLICATE"
    assert "confirmed locally" in reason


def test_same_normalized_url_is_always_confirmed(monkeypatch):
    monkeypatch.setattr(rc80, "_local_duplicate_hit", lambda *_a: None)
    a = {"source_id": 1, "title": "A", "raw_text": "x", "normalized_url": "https://x.test/a"}
    b = {"source_id": 1, "title": "B", "raw_text": "y", "normalized_url": "https://x.test/a"}
    relation, reason = rc80._guard_relation_rc80(a, b, "UPDATE", "AI update")
    assert relation == "UPDATE"
    assert "same normalized URL" in reason


class _MiniDb:
    def __init__(self, path: Path):
        self.path = path
        con = sqlite3.connect(path)
        con.executescript(
            """
            CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE articles(
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                event_cluster_id INTEGER,
                cluster_parent_id INTEGER,
                duplicate_of INTEGER,
                reject_reason TEXT,
                last_error TEXT,
                processing_started_at TEXT,
                next_retry_at TEXT
            );
            """
        )
        con.commit(); con.close()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        try:
            yield con
            con.commit()
        finally:
            con.close()


def test_recent_cluster_repair_is_one_time_and_does_not_touch_old_rows(tmp_path):
    db = _MiniDb(tmp_path / "rc80.sqlite3")
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    old = (now - timedelta(days=8)).isoformat(timespec="seconds")
    with db.connect() as con:
        con.execute("INSERT INTO articles VALUES(1,'clustered',?,5,9,NULL,'x','y','z','q')", (recent,))
        con.execute("INSERT INTO articles VALUES(2,'clustered',?,6,10,NULL,'x','y','z','q')", (old,))

    assert rc80.repair_rc80_recent_clusters(db, 72) == 1
    with db.connect() as con:
        a = con.execute("SELECT status,event_cluster_id,cluster_parent_id FROM articles WHERE id=1").fetchone()
        b = con.execute("SELECT status,event_cluster_id,cluster_parent_id FROM articles WHERE id=2").fetchone()
    assert a == ("new", None, None)
    assert b == ("clustered", 6, 10)
    assert rc80.repair_rc80_recent_clusters(db, 72) == 0
