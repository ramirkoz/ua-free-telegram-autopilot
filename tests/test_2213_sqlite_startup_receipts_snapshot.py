from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from telegram_autopilot.v2.startup_database_gate import ExistingDatabaseUnreadable, configured_channel_count
from telegram_autopilot.v2.operator_data_snapshot import export_operator_data_snapshot
from telegram_autopilot.v2.delivery_integrity import delivery_integrity_snapshot
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed(tmp_path):
    store=V2Store(tmp_path/"operator.sqlite3")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,enabled,created_at,updated_at) VALUES(1,'CTRL','PRIVATE_TARGET',1,?,?)",(now_iso(),now_iso()))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled) VALUES(1,1,'rss','Example','https://example.org',1)")
        con.execute("INSERT INTO articles(id,channel_id,source_id,external_id,title,source_url,raw_text,discovered_at,stage,decision,last_error_detail) VALUES(99,1,1,'example','Public title','https://example.org/story','Public source',?,'PUBLISHED','PUBLISH','BOT_TOKEN_SECRET')",(now_iso(),))
        con.execute("INSERT INTO publication_delivery_journal(article_id,channel_id,state,primary_message_id,committed_at,updated_at,last_error) VALUES(99,1,'COMMITTED','900',?,?,'BOT_TOKEN_SECRET')",(now_iso(),now_iso()))
    return store


def test_existing_database_skips_import_and_unreadable_database_fails_closed(tmp_path):
    store=_seed(tmp_path)
    assert configured_channel_count(store.path)==1
    bad=tmp_path/"unreadable.sqlite3"
    bad.write_bytes(b"invalid sqlite file")
    with pytest.raises(ExistingDatabaseUnreadable):
        configured_channel_count(bad)


def test_receipts_survive_article_cascade_without_digest_change(tmp_path):
    store=_seed(tmp_path)
    before=delivery_integrity_snapshot(store)
    with store.connect() as con:
        con.execute("DELETE FROM articles WHERE id=99")
        assert con.execute("SELECT COUNT(*) FROM publication_delivery_journal").fetchone()[0]==0
        assert con.execute("SELECT article_id,state FROM delivery_receipt_archive").fetchone()["article_id"]==99
    after=delivery_integrity_snapshot(store)
    assert before["committed_count"]==after["committed_count"]==1
    assert before["committed_receipts_sha256"]==after["committed_receipts_sha256"]
    assert store.delivery_journal_summary()["counts"]["COMMITTED"]==1


def test_redacted_snapshot_has_public_content_but_no_secrets(tmp_path):
    store=_seed(tmp_path)
    destination=tmp_path/"diagnostic.sqlite3"
    result=export_operator_data_snapshot(store.path,destination)
    assert result["rows"]["articles"]==1
    with sqlite3.connect(destination) as con:
        assert con.execute("SELECT title,raw_text FROM articles").fetchone()==("Public title","Public source")
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "meta" not in tables and "secrets" not in tables
        assert "telegram_chat_id" not in [r[1] for r in con.execute("PRAGMA table_info(channels)")]
        assert "last_error" not in [r[1] for r in con.execute("PRAGMA table_info(publication_delivery_journal)")]
        assert con.execute("PRAGMA quick_check").fetchone()[0]=="ok"
    raw=destination.read_bytes()
    assert b"PRIVATE_TARGET" not in raw
    assert b"BOT_TOKEN_SECRET" not in raw
