"""2.2.29 commercial portfolio: immutable scope and durable Data regression."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from telegram_autopilot.v2.commercial_sources_229 import (
    META_PREFIX,
    RETIRE_LOW_YIELD,
    SOURCE_ADDITIONS,
    apply_commercial_sources_229,
)


class Store:
    def __init__(self, path: Path):
        self.path = path
        with self.transaction() as con:
            con.executescript("""
                CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE channels(
                    id INTEGER PRIMARY KEY,name TEXT,editorial_runtime_profile TEXT,
                    min_publish_interval_minutes INTEGER,editorial_thresholds_json TEXT
                );
                CREATE TABLE sources(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER,kind TEXT,name TEXT,url TEXT,
                    enabled INTEGER,initialized INTEGER DEFAULT 0,
                    priority INTEGER,last_checked_at TEXT DEFAULT '',
                    last_error TEXT DEFAULT '',
                    legacy_config_json TEXT DEFAULT '{}',
                    UNIQUE(channel_id,url)
                );
                CREATE TABLE articles(
                    id INTEGER PRIMARY KEY,channel_id INTEGER,
                    source_id INTEGER,stage TEXT,raw_text TEXT
                );
            """)
            con.execute("INSERT INTO channels VALUES(1,'CTRL+UA','standard',45,'{}')")
            con.execute("INSERT INTO channels VALUES(2,'ПРОДАНО!','commercial_editorial',30,'{\"broad_interest_fit\":45}')")
            con.execute("INSERT INTO channels VALUES(3,'ЗАПОРІЖЖЯ | ГРОМАДИ','standard',5,'{}')")
            fixture = [
                (1,"CTRL seed","https://test.example/","rss",1,77),
                (2,"Springwise",RETIRE_LOW_YIELD["Springwise"],"page",1,160),
                (2,"Snapchat for Business",RETIRE_LOW_YIELD["Snapchat for Business"],"page",1,30),
                (2,"YouTube Blog",RETIRE_LOW_YIELD["YouTube Blog"],"page",1,10),
                (2,"Famous Campaigns","https://www.famouscampaigns.com/feed/","rss",1,99),
                (2,"Muse by Clio","https://musebyclios.com/feed/","rss",1,100),
                (2,"My hand-added source","https://unrelated.example/myfeed","rss",1,17),
                (2,"My ad-free source","https://another.example/feed","rss",0,5),
                (3,"Civic seed","https://civic.example/","rss",1,50),
            ]
            for cid,name,url,kind,enabled,priority in fixture:
                con.execute(
                    "INSERT INTO sources(channel_id,name,url,kind,enabled,priority) VALUES(?,?,?,?,?,?)",
                    (cid,name,url,kind,enabled,priority)
                )
            # Original article relation must remain valid: no DELETE and no IDs reset.
            con.execute("INSERT INTO articles VALUES(50,2,5,'PUBLISHED','a durable article')")
            con.commit()

    def transaction(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con


def test_commercial_refresh_scoped_and_idempotent(tmp_path):
    store = Store(tmp_path / "current.sqlite3")
    first = apply_commercial_sources_229(store)
    assert first["channels"][0]["outcome"] == "applied"
    assert len(first["channels"][0]["added"]) == len(SOURCE_ADDITIONS)
    second = apply_commercial_sources_229(store)
    assert second["channels"][0]["outcome"] == "already_applied"
    with store.transaction() as con:
        sources = con.execute("SELECT * FROM sources WHERE channel_id=2").fetchall()
        assert len(sources) == 8 + len(SOURCE_ADDITIONS) - 2 # 6 initial commercial + additions
        by_name = {row["name"]: row for row in sources}
        assert by_name["Springwise"]["enabled"] == 0
        assert by_name["Snapchat for Business"]["enabled"] == 0
        assert by_name["YouTube Blog"]["enabled"] == 0
        assert by_name["Famous Campaigns"]["url"] == "https://www.famouscampaigns.com/"
        assert by_name["Famous Campaigns"]["kind"] == "page"
        assert by_name["Famous Campaigns"]["priority"] == 10
        assert by_name["My hand-added source"]["enabled"] == 1
        assert by_name["My hand-added source"]["priority"] == 17
        assert by_name["My ad-free source"]["enabled"] == 0
        assert by_name["Muse by Clio"]["priority"] == 14
        assert con.execute("SELECT source_id,stage FROM articles WHERE id=50").fetchone()["source_id"] == 5
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id=1").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id=3").fetchone()[0] == 1
        for channel_id, expected in [(1,45),(2,30),(3,5)]:
            row = con.execute("SELECT min_publish_interval_minutes FROM channels WHERE id=?", (channel_id,)).fetchone()
            assert row[0] == expected
        assert con.execute("SELECT editorial_thresholds_json FROM channels WHERE id=2").fetchone()[0] == '{"broad_interest_fit":45}'
        assert con.execute("SELECT count(*) FROM meta WHERE key=?", (META_PREFIX + "2",)).fetchone()[0] == 1


def test_custom_commercial_sources_are_not_rewritten(tmp_path):
    store = Store(tmp_path / "custom.sqlite3")
    with store.transaction() as con:
        con.execute("DELETE FROM sources WHERE channel_id=2 AND name IN ('Springwise','Snapchat for Business','YouTube Blog','Famous Campaigns','Muse by Clio')")
        con.commit()
    result = apply_commercial_sources_229(store)
    assert result["channels"][0]["outcome"] == "custom_sources_unchanged"
    with store.transaction() as con:
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id=2").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM meta WHERE key=?", (META_PREFIX + "2",)).fetchone()[0] == 0


def test_existing_alternative_domain_is_not_duplicated(tmp_path):
    store = Store(tmp_path / "alternative.sqlite3")
    with store.transaction() as con:
        con.execute(
            "INSERT INTO sources(channel_id,name,url,kind,enabled,priority) VALUES(2,'My Creative Bloq','https://www.creativebloq.com/custom','page',0,99)"
        )
        con.commit()
    apply_commercial_sources_229(store)
    with store.transaction() as con:
        all_sources = con.execute("SELECT name,url FROM sources WHERE channel_id=2").fetchall()
        assert not any(r["name"] == "Creative Bloq" for r in all_sources)
        assert any(r["name"] == "My Creative Bloq" for r in all_sources)
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id=2 AND url LIKE '%creativebloq.com%'").fetchone()[0] == 1
