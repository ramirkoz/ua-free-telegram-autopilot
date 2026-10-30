"""2.2.61: operator-known, scoped, history-preserving syndicated feed recovery."""
import inspect
import json
import sqlite3
from pathlib import Path

from telegram_autopilot.v2.commercial_feed_recovery_261 import (
    recover_commercial_feed_261, OLD_URL, PUBLIC_SYNDICATED_RSS, MARKER,
)
from telegram_autopilot.v2.main import main


class Store:
    def __init__(self, db: Path):
        self.db = db
        with self.transaction() as con:
            con.executescript("""
            CREATE TABLE channels(id INTEGER PRIMARY KEY,editorial_runtime_profile TEXT);
            CREATE TABLE sources(
                id INTEGER PRIMARY KEY,channel_id INTEGER,name TEXT,url TEXT,kind TEXT,
                enabled INTEGER,initialized INTEGER,priority INTEGER,
                last_error TEXT,last_checked_at TEXT,legacy_config_json TEXT,
                UNIQUE(channel_id,url)
            );
            CREATE TABLE source_health(
                source_id INTEGER PRIMARY KEY,consecutive_failures INTEGER,cooldown_until TEXT,
                last_outcome TEXT,last_error TEXT,zero_result_streak INTEGER,slow_streak INTEGER,
                last_duration_ms INTEGER,last_items INTEGER,last_added INTEGER,updated_at TEXT,
                success_count INTEGER,failure_count INTEGER
            );
            CREATE TABLE articles(id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,stage TEXT);
            CREATE TABLE publication_delivery_journal(id INTEGER PRIMARY KEY,article_id INTEGER,result TEXT);
            INSERT INTO channels VALUES(1,'standard');
            INSERT INTO channels VALUES(2,'commercial_editorial');
            INSERT INTO channels VALUES(3,'standard');
            INSERT INTO sources VALUES(201,2,'Design Milk','https://design-milk.com/feed/','rss',
                                      1,1,25,'HTTP 403','2026-10-20T12:00:00+02:00','{}');
            INSERT INTO sources VALUES(202,1,'Design Milk','https://design-milk.com/feed/','rss',
                                      1,1,10,'HTTP 403','2026-10-20T12:00:00+02:00','{}');
            INSERT INTO sources VALUES(203,2,'Custom','https://example.org/custom','rss',
                                      1,1,99,'','2026-10-20T12:00:00+02:00','{}');
            INSERT INTO source_health VALUES(201,7,'2026-10-31T09:00:00+02:00','HTTP_403','403',
                                             0,0,610,0,0,'',5,7);
            INSERT INTO source_health VALUES(202,7,'2026-10-31T09:00:00+02:00','HTTP_403','403',
                                             0,0,610,0,0,'',5,7);
            INSERT INTO source_health VALUES(203,0,'','KNOWN_ONLY','',0,0,1234,5,0,'',12,0);
            INSERT INTO articles VALUES(987,2,201,'PUBLISHED');
            INSERT INTO publication_delivery_journal VALUES(2,987,'COMMITTED');
            """)
            con.commit()

    def transaction(self):
        c=sqlite3.connect(self.db)
        c.row_factory=sqlite3.Row
        return c


def test_exact_source_migrates_preserving_article_receipts_and_other_channels(tmp_path):
    store=Store(tmp_path/"test.db")
    result=recover_commercial_feed_261(store)
    assert result["changed"] == 1
    with store.transaction() as con:
        src=con.execute("SELECT * FROM sources WHERE id=201").fetchone()
        health=con.execute("SELECT * FROM source_health WHERE source_id=201").fetchone()
        assert src["url"]==PUBLIC_SYNDICATED_RSS
        assert src["priority"]==25 and src["initialized"]==1 and src["last_checked_at"]==""
        assert json.loads(src["legacy_config_json"])[MARKER]["operator_network_verified"] is False
        assert health["cooldown_until"]=="" and health["consecutive_failures"]==0
        assert health["success_count"]==5 and health["failure_count"]==7
        assert con.execute("SELECT source_id FROM articles WHERE id=987").fetchone()[0]==201
        assert con.execute("SELECT result FROM publication_delivery_journal WHERE article_id=987").fetchone()[0]=="COMMITTED"
        assert con.execute("SELECT url FROM sources WHERE id=202").fetchone()[0]==OLD_URL
        assert con.execute("SELECT last_outcome FROM source_health WHERE source_id=202").fetchone()[0]=="HTTP_403"
        assert con.execute("SELECT url FROM sources WHERE id=203").fetchone()[0]=="https://example.org/custom"
    assert recover_commercial_feed_261(store)["changed"]==0


def test_not_migrate_healthy_or_operator_modified_sources(tmp_path):
    store=Store(tmp_path/"healthy.db")
    with store.transaction() as con:
        con.execute("UPDATE source_health SET last_outcome='OK' WHERE source_id=201")
        con.commit()
    assert recover_commercial_feed_261(store)["changed"]==0
    with store.transaction() as con:
        con.execute("UPDATE source_health SET last_outcome='HTTP_403' WHERE source_id=201")
        con.execute("UPDATE sources SET url='https://design-milk.com/custom' WHERE id=201")
        con.commit()
    assert recover_commercial_feed_261(store)["changed"]==0


def test_conflict_must_never_merge_two_source_ids(tmp_path):
    store=Store(tmp_path/"collision.db")
    with store.transaction() as con:
        con.execute("UPDATE sources SET url=? WHERE id=203",(PUBLIC_SYNDICATED_RSS,))
        con.commit()
    result=recover_commercial_feed_261(store)
    assert result["changed"]==0
    assert result["sources"][0]["status"]=="existing_feed_conflict_no_change"


def test_startup_hook_exists_before_runtime_workers():
    source=inspect.getsource(main)
    assert "recover_commercial_feed_261(store)" in source
    assert source.index("recover_commercial_feed_261(store)") < source.index("runtime = RuntimeEngine(store)")


def test_no_dynamic_403_evasion_and_no_extra_ai_budget():
    import telegram_autopilot.v2.commercial_feed_recovery_261 as module
    source=inspect.getsource(module)
    assert "fetch_url(" not in source and "subprocess" not in source
    assert "UPDATE channels" not in source
    assert "DELETE FROM" not in source
