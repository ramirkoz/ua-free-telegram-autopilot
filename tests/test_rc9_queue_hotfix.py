from __future__ import annotations

import sqlite3
from pathlib import Path

from telegram_autopilot.database import Database
from telegram_autopilot.queue_hotfix import install_queue_hotfix


install_queue_hotfix()


def _seed_queue(db: Database, *, retry_rows: int, new_rows: int) -> int:
    with db.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,editorial_profile,enabled,include_source_link,poll_interval_minutes,min_publish_interval_minutes,dedupe_window_hours,max_age_hours,max_posts_per_cycle,created_at,updated_at) VALUES(1,'Queue','@queue','tech',1,0,5,0,72,24,3,'x','x')"
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized) VALUES(1,1,'rss','Feed','https://example.com/feed',1,1)"
        )
        article_id = 1
        for _ in range(retry_rows):
            con.execute(
                "INSERT INTO articles(id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,discovered_at,status,last_error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (article_id,1,1,f'r{article_id}',f'Retry {article_id}',f'https://example.com/r{article_id}',f'https://example.com/r{article_id}','text',f'h{article_id}','2026-08-17T10:00:00+00:00','retry','old AI failure'),
            )
            article_id += 1
        first_new = article_id
        for _ in range(new_rows):
            con.execute(
                "INSERT INTO articles(id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,discovered_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (article_id,1,1,f'n{article_id}',f'New {article_id}',f'https://example.com/n{article_id}',f'https://example.com/n{article_id}','text',f'h{article_id}','2026-08-17T11:00:00+00:00','new'),
            )
            article_id += 1
    return first_new


def test_hotfix_adds_retry_columns_without_resetting_database(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    db = Database(path)
    _seed_queue(db, retry_rows=1, new_rows=1)
    before = [(r["id"], r["status"]) for r in db.history(1, limit=10)]
    Database(path)
    with sqlite3.connect(path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(articles)")}
    after = [(r["id"], r["status"]) for r in db.history(1, limit=10)]
    assert {"retry_count", "next_retry_at"} <= columns
    assert before == after


def test_new_rows_have_absolute_priority_over_old_retry_rows(tmp_path: Path):
    db = Database(tmp_path / "queue.sqlite3")
    first_new = _seed_queue(db, retry_rows=40, new_rows=17)
    rows = db.pending_articles(1, limit=30)
    assert [r["status"] for r in rows[:17]] == ["new"] * 17
    assert [r["id"] for r in rows[:17]] == list(range(first_new, first_new + 17))


def test_failed_retry_gets_backoff_and_leaves_immediate_queue(tmp_path: Path):
    db = Database(tmp_path / "backoff.sqlite3")
    _seed_queue(db, retry_rows=1, new_rows=0)
    db.update_article(1, status="retry", last_error="temporary AI failure")
    row = db.get_article(1)
    assert row["status"] == "retry"
    assert row["retry_count"] == 1
    assert row["next_retry_at"]
    assert db.pending_articles(1, limit=10) == []


def test_retry_is_bounded_and_moves_to_error_after_five_failures(tmp_path: Path):
    db = Database(tmp_path / "bounded.sqlite3")
    _seed_queue(db, retry_rows=1, new_rows=0)
    for _ in range(5):
        db.update_article(1, status="retry", last_error="AI unavailable")
    row = db.get_article(1)
    assert row["status"] == "error"
    assert row["retry_count"] == 5
    assert row["next_retry_at"] is None


def test_successful_intermediate_retry_does_not_increment_failure_counter(tmp_path: Path):
    db = Database(tmp_path / "resume.sqlite3")
    _seed_queue(db, retry_rows=0, new_rows=1)
    db.update_article(1, status="retry", headline_uk="Готово", last_error=None)
    row = db.get_article(1)
    assert row["status"] == "retry"
    assert row["retry_count"] == 0
    assert row["next_retry_at"] is None
