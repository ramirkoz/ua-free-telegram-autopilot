from __future__ import annotations

import sqlite3
from pathlib import Path

from telegram_autopilot.v2.migration_service import MigrationManager
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_v2(path: Path) -> None:
    store = V2Store(path)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at)
               VALUES(1,'LIVE RC85','@live',1,'editorial',?,?)""",
            (stamp, stamp),
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,?)", (stamp,))
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled)
               VALUES(1,1,'telegram','Live source','https://t.me/live',1)"""
        )
        con.execute(
            """INSERT INTO articles(id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                       content_hash,discovered_at,stage,decision,blocked_by,final_text,published_at,telegram_message_id)
               VALUES(1,1,1,'x','Published','https://t.me/live/1','https://t.me/live/1','Raw','h',?,
                      'PUBLISHED','PUBLISH','NONE','Final',?,'100')""",
            (stamp, stamp),
        )


def _seed_wrong_legacy(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """CREATE TABLE channels(id INTEGER PRIMARY KEY,name TEXT);
               CREATE TABLE sources(id INTEGER PRIMARY KEY,channel_id INTEGER,name TEXT,url TEXT);
               CREATE TABLE articles(id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,title TEXT);
            """
        )
        con.commit()
    finally:
        con.close()


def test_portable_root_prefers_v2_database_when_old_legacy_db_is_also_present(tmp_path: Path) -> None:
    old_root = tmp_path / "rc85"
    data = old_root / "Data"
    data.mkdir(parents=True)
    _seed_v2(data / "telegram_autopilot_v2.sqlite3")
    _seed_wrong_legacy(data / "telegram_autopilot.sqlite3")

    target = tmp_path / "rc88" / "Data" / "telegram_autopilot_v2.sqlite3"
    V2Store(target)
    report, _, _ = MigrationManager(target).import_legacy_atomic(old_root, import_credentials=False)

    assert report.channels_imported == 1
    assert report.sources_imported == 1
    assert report.articles_imported == 1
    with sqlite3.connect(target) as con:
        assert con.execute("SELECT name FROM channels WHERE id=1").fetchone()[0] == "LIVE RC85"
        assert con.execute("SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED'").fetchone()[0] == 1


def test_v2_carry_forward_preserves_database_rows_exactly(tmp_path: Path) -> None:
    old_root = tmp_path / "rc85"
    data = old_root / "Data"
    data.mkdir(parents=True)
    source = data / "telegram_autopilot_v2.sqlite3"
    _seed_v2(source)

    target = tmp_path / "rc88" / "Data" / "telegram_autopilot_v2.sqlite3"
    V2Store(target)
    report, _, _ = MigrationManager(target).import_legacy_atomic(data, import_credentials=False)

    assert report.published_imported == 1
    with sqlite3.connect(target) as con:
        assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
