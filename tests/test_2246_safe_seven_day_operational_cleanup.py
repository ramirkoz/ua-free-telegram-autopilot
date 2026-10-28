"""Autopilot 2.2.46: real operator 7-day backlog cleanup, no receipt loss.

An old source_published_at may be future or malformed; supervisor's 7-day
metric is based on discovered_at, so retention must agree. UNKNOWN deliveries
are permanently quarantined, COMMITTED message identities survive deletion.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from telegram_autopilot.v2.delivery_integrity import delivery_integrity_snapshot
from telegram_autopilot.v2.startup_background_hotfix import _run_batched_retention
from telegram_autopilot.v2.storage import V2Store, now_iso


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _seed(store: V2Store) -> None:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,published_dedupe_window_hours,
                   created_at,updated_at)
               VALUES(1,'Science','@science',720,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','source','https://example.org/rss')"
        )


def _article(
    store: V2Store, article_id: int, days: int, *,
    source_published_at: str = "", stage: str = "REJECTED",
    duplicate_of: int | None = None,
) -> None:
    with store.connect() as con:
        con.execute(
            """INSERT INTO articles(
                   id,channel_id,source_id,external_id,title,source_url,
                   raw_text,discovered_at,source_published_at,stage,
                   decision,duplicate_of,final_text)
               VALUES(?,1,1,?,?,?,?,?,?,?,?,?,?)""",
            (
                article_id, f"article-{article_id}", f"Title {article_id}",
                f"https://example.org/{article_id}", "Large source blob " * 15,
                _ago(days), source_published_at, stage,
                "PUBLISH" if stage == "PUBLISHED" else "REJECT",
                duplicate_of, "Written final",
            ),
        )


def test_246_actual_operator_stale_metric_repaired_even_with_bad_source_dates(tmp_path):
    store = V2Store(tmp_path / "operator.sqlite3")
    _seed(store)
    _article(store, 100, 9, source_published_at="2099-01-01T00:00:00+00:00")
    _article(store, 101, 9, source_published_at="not-a-date")
    _article(store, 102, 1, source_published_at=_ago(14))
    with store.connect() as con:
        con.execute(
            "INSERT INTO jobs(article_id,channel_id,available_at,created_at,updated_at) VALUES(100,1,?,?,?)",
            (now_iso(), now_iso(), now_iso()),
        )

    result = _run_batched_retention(store)
    assert result["articles_purged"] == 2
    assert result["remaining_eligible"] == 0
    assert store.get_article(100) is None
    assert store.get_article(101) is None
    assert store.get_article(102) is not None
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE article_id=100").fetchone()[0] == 0
        assert con.execute("SELECT published_dedupe_window_hours FROM channels WHERE id=1").fetchone()[0] == 720
        saved = con.execute("SELECT value FROM meta WHERE key='retention_246_last_run_json'").fetchone()[0]
    assert json.loads(saved)["articles_purged"] == 2
    assert _run_batched_retention(store)["articles_purged"] == 0


def test_246_committed_receipts_archive_exact_digest_and_event_memory(tmp_path):
    store = V2Store(tmp_path / "operator.sqlite3")
    _seed(store)
    _article(store, 202, 9, stage="PUBLISHED")
    _article(store, 204, 9, stage="REJECTED")
    with store.connect() as con:
        con.execute(
            """INSERT INTO publication_delivery_journal(
                 article_id,channel_id,state,mode,primary_message_id,committed_at,updated_at)
               VALUES(202,1,'COMMITTED','text','1533',?,?)""",
            (_ago(9), _ago(9)),
        )
        con.execute(
            """INSERT INTO event_publication_history(
                 article_id,event_id,channel_id,title,raw_text,source_published_at,
                 published_at,facts_json,committed)
               VALUES(202,'city_event_202',1,'First published', 'original facts', ?, ?, '{}',1)""",
            (_ago(9), _ago(9)),
        )

    before = delivery_integrity_snapshot(store)
    result = _run_batched_retention(store)
    after = delivery_integrity_snapshot(store)
    assert result["articles_purged"] == 2
    assert before["committed_count"] == after["committed_count"] == 1
    assert before["committed_receipts_sha256"] == after["committed_receipts_sha256"]
    with store.connect() as con:
        assert con.execute(
            "SELECT state,primary_message_id FROM delivery_receipt_archive WHERE article_id=202"
        ).fetchone()[:] == ("COMMITTED", "1533")
        assert con.execute("SELECT COUNT(*) FROM publication_delivery_journal WHERE article_id=202").fetchone()[0] == 0
        assert con.execute("SELECT raw_text FROM event_publication_history WHERE article_id=202").fetchone()[0] == "original facts"


@pytest.mark.parametrize("state", ["UNKNOWN", "FAILED", "PREPARED", "SENDING"])
def test_246_never_delete_unresolved_delivery_or_its_article(tmp_path, state):
    store = V2Store(tmp_path / "operator.sqlite3")
    _seed(store)
    _article(store, 66297, 19, stage="READY")
    _article(store, 300, 8)
    with store.connect() as con:
        con.execute(
            """INSERT INTO publication_delivery_journal(
                  article_id,channel_id,state,primary_message_id,updated_at)
               VALUES(66297,1,?,'',?)""",
            (state, _ago(15)),
        )
    result = _run_batched_retention(store)
    assert result["articles_purged"] == 1
    assert result["protected_uncertain"] == 1
    assert result["remaining_eligible"] == 0
    assert store.get_article(66297) is not None
    assert store.get_article(300) is None
    with store.connect() as con:
        assert con.execute("SELECT state FROM publication_delivery_journal WHERE article_id=66297").fetchone()[0] == state
        assert con.execute("SELECT COUNT(*) FROM delivery_receipt_archive WHERE article_id=66297").fetchone()[0] == 0


def test_246_detaches_recent_duplicate_without_dropping_new_work(tmp_path):
    store = V2Store(tmp_path / "operator.sqlite3")
    _seed(store)
    _article(store, 401, 9)
    _article(store, 402, 1, duplicate_of=401)
    result = _run_batched_retention(store)
    assert result["duplicate_links_detached"] >= 1
    assert store.get_article(401) is None
    assert store.get_article(402) is not None
    with store.connect() as con:
        assert con.execute("SELECT duplicate_of FROM articles WHERE id=402").fetchone()[0] is None


def test_246_bounded_pass_keeps_progress_for_next_cycle(tmp_path, monkeypatch):
    import telegram_autopilot.v2.startup_background_hotfix as maintenance
    store = V2Store(tmp_path / "operator.sqlite3")
    _seed(store)
    for id in range(50, 60):
        _article(store, id, 10)
    monkeypatch.setattr(maintenance, "_BATCH_SIZE", 2)
    monkeypatch.setattr(maintenance, "_MAX_BATCHES_PER_PASS", 2)
    monkeypatch.setattr(maintenance.time, "sleep", lambda *_: None)
    first = maintenance._run_batched_retention(store)
    assert first["articles_purged"] == 4
    assert first["remaining_eligible"] == 6
    rest = sum(maintenance._run_batched_retention(store)["articles_purged"] for _ in range(3))
    assert rest == 6
    assert maintenance._run_batched_retention(store)["remaining_eligible"] == 0


def test_246_no_live_vacuum_or_operator_dedupe_setting_changes():
    import inspect
    import telegram_autopilot.v2.startup_background_hotfix as maintenance
    src = inspect.getsource(maintenance._run_batched_retention)
    assert 'VACUUM' not in src.replace("No live VACUUM", "")
    assert "UPDATE channels SET published_dedupe_window_hours" not in src
    assert maintenance._BACKGROUND_DELAY_SECONDS >= 120
    assert maintenance._PERIODIC_RETENTION_SECONDS >= 900
