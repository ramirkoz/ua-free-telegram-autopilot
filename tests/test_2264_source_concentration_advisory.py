"""v2.2.64: commercial source concentration is advisory, never a quota."""
from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3

from telegram_autopilot.v2.commercial_topic_balance_258 import commercial_topic_advisory_258


class ReadOnlyFeed:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE articles(
              id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,
              title TEXT,final_text TEXT,stage TEXT,published_at TEXT
            );
            INSERT INTO sources VALUES(199,'Yanko Design');
            INSERT INTO sources VALUES(129,'Campaign Brief');
        """)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [
            (i, 2, 199 if i <= 15 else 129, f"Unrelated headline {i}",
             "Different published story", "PUBLISHED", stamp)
            for i in range(1, 21)
        ]
        self.db.executemany("INSERT INTO articles VALUES(?,?,?,?,?,?,?)", rows)
        self.db.commit()

    @contextmanager
    def connect(self):
        yield self.db


def test_dominant_source_unknown_theme_receives_story_context():
    store = ReadOnlyFeed()
    before = store.db.total_changes
    advice = commercial_topic_advisory_258(
        store, 2, {"title": "An unusual new product", "source_id": 199}
    )
    assert "75%" in advice
    assert "НЕ квота" in advice
    assert "новий" in advice
    assert store.db.total_changes == before


def test_independent_source_is_not_disfavored():
    store = ReadOnlyFeed()
    assert commercial_topic_advisory_258(
        store, 2, {"title": "An unusual new product", "source_id": 129}
    ) == ""
    assert commercial_topic_advisory_258(
        store, 2, {"title": "An unusual new product"}
    ) == ""
