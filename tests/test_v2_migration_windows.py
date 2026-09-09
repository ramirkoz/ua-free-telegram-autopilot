from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from telegram_autopilot.v2.migration_service import MigrationManager
from telegram_autopilot.v2.storage import V2Store


def _make_legacy(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE channels(
                id INTEGER PRIMARY KEY,name TEXT,telegram_chat_id TEXT,enabled INTEGER,
                channel_mode TEXT,min_publish_interval_minutes INTEGER,created_at TEXT,updated_at TEXT
            );
            CREATE TABLE channel_policies(
                channel_id INTEGER PRIMARY KEY,enabled INTEGER,purpose TEXT,audience TEXT,
                selection_rules TEXT,rejection_rules TEXT,writing_rules TEXT,style_rules TEXT,
                positive_examples TEXT,negative_examples TEXT,extra_instructions TEXT,
                selector_extra_prompt TEXT,writer_extra_prompt TEXT,media_policy TEXT,
                target_min_chars INTEGER,target_max_chars INTEGER,updated_at TEXT
            );
            CREATE TABLE sources(
                id INTEGER PRIMARY KEY,channel_id INTEGER,kind TEXT,name TEXT,url TEXT,
                enabled INTEGER,initialized INTEGER,priority INTEGER,last_checked_at TEXT,last_error TEXT
            );
            CREATE TABLE articles(
                id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,external_id TEXT,
                title TEXT,url TEXT,normalized_url TEXT,raw_text TEXT,content_hash TEXT,
                source_published_at TEXT,discovered_at TEXT,status TEXT,published_at TEXT,
                telegram_message_id TEXT,media_json TEXT,article_layout_json TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO channels VALUES(1,'CTRL+UA','@ctrl',1,'editorial',11,?,?)",
            ('2026-09-01T00:00:00+00:00','2026-09-09T00:00:00+00:00'),
        )
        con.execute(
            "INSERT INTO channel_policies VALUES(1,1,'tech','UA','include research','exclude promo','write concise','human','','','','','','preferred',280,780,?)",
            ('2026-09-09T00:00:00+00:00',),
        )
        con.execute(
            "INSERT INTO sources VALUES(1,1,'rss','Source','https://example.com/feed',1,1,100,'','')"
        )
        con.execute(
            """INSERT INTO articles(
                id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,
                source_published_at,discovered_at,status,published_at,telegram_message_id,media_json,article_layout_json
            ) VALUES(10,1,1,'p','Published','https://example.com/p','https://example.com/p','facts','h1',
                '2026-09-08T12:00:00+00:00','2026-09-08T12:00:00+00:00','published',
                '2026-09-08T13:00:00+00:00','555','[]','{}')"""
        )
        con.commit()
    finally:
        con.close()


def test_migration_does_not_use_os_replace(tmp_path: Path, monkeypatch) -> None:
    legacy = tmp_path / 'legacy.sqlite3'
    target_path = tmp_path / 'telegram_autopilot_v2.sqlite3'
    _make_legacy(legacy)
    V2Store(target_path)

    def forbidden_replace(*args, **kwargs):
        raise OSError(32, 'The process cannot access the file because it is being used by another process')

    monkeypatch.setattr(os, 'replace', forbidden_replace)
    report, backup, _ = MigrationManager(target_path).import_legacy_atomic(
        legacy,
        import_credentials=False,
    )

    assert report.channels_imported == 1
    assert report.sources_imported == 1
    assert report.published_imported == 1
    assert backup is not None and backup.exists()

    store = V2Store(target_path)
    channel = store.get_channel(1)
    assert channel is not None
    assert channel.name == 'CTRL+UA'
    with store.connect() as con:
        row = con.execute("SELECT stage,published_at FROM articles WHERE legacy_article_id=10").fetchone()
    assert row is not None
    assert row['stage'] == 'PUBLISHED'
    assert row['published_at'] == '2026-09-08T13:00:00+00:00'


def test_second_import_is_not_blocked_by_stale_temp_filename(tmp_path: Path) -> None:
    legacy = tmp_path / 'legacy.sqlite3'
    target_path = tmp_path / 'telegram_autopilot_v2.sqlite3'
    _make_legacy(legacy)
    V2Store(target_path)

    stale = target_path.with_name(target_path.name + '.migration.tmp')
    stale.write_bytes(b'locked-looking-stale-file')

    manager = MigrationManager(target_path)
    first, _, _ = manager.import_legacy_atomic(legacy, import_credentials=False)
    second, _, _ = manager.import_legacy_atomic(legacy, import_credentials=False)

    assert first.channels_imported == 1
    assert second.channels_imported == 1
    assert stale.read_bytes() == b'locked-looking-stale-file'
