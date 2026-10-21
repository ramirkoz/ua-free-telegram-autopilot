"""v2.2.16 operator P1: strict freshness across feeds, no invented-name QA false alarms."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from telegram_autopilot.fact_guard import (
    _protected_latin_tokens, validate_fact_guard, FactGuardError,
)
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_backlog(tmp_path, *, old_priority: int, fresh_priority: int,
                  old_hours: int = 22, fresh_hours: int = 1, old_count: int = 40):
    store = V2Store(tmp_path / "operator.sqlite3")
    now = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,
                min_publish_interval_minutes,publish_24h,publish_start,publish_end,
                max_age_hours,created_at,updated_at)
                VALUES(1,'CTRL','',1,45,0,'08:00','20:00',24,?,?)""",
            (now, now),
        )
        for source_id, priority in ((1, old_priority), (2, fresh_priority)):
            con.execute(
                """INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority)
                   VALUES(?,1,'rss','Example','https://example.org/rss-' || ?,1,1,?)""",
                (source_id, source_id, priority),
            )
        for i in range(old_count + 1):
            fresh = i == old_count
            stamp = (datetime.now(timezone.utc) - timedelta(
                hours=fresh_hours if fresh else old_hours)).isoformat()
            sid = 2 if fresh else 1
            priority = fresh_priority if fresh else old_priority
            aid = con.execute(
                """INSERT INTO articles(channel_id,source_id,external_id,title,
                  source_url,canonical_source_url,raw_text,source_published_at,
                  discovered_at,stage,decision)
                  VALUES(1,?,?,?,?,?,?,?,?,'COLLECTED','PENDING')""",
                (sid, f"item-{i}", f"news-{i}", f"https://example.org/{i}",
                 f"https://example.org/{i}", f"news-{i}", stamp, now),
            ).lastrowid
            con.execute(
                """INSERT INTO jobs(article_id,channel_id,job_type,state,
                    priority,available_at,created_at,updated_at)
                    VALUES(?,1,'process','QUEUED',?,?,?,?)""",
                (int(aid),priority,now,now,now),
            )
    return store


def _picked_source(store):
    claimed=store.claim_job(channel_id=1,worker_id="regression")
    assert claimed is not None
    with store.connect() as con:
        return int(con.execute(
            "SELECT source_id FROM articles WHERE id=?", (claimed["article_id"],)
        ).fetchone()[0])


def test_overload_fresh_source_beats_old_high_priority_even_if_low_priority(tmp_path):
    store=_seed_backlog(tmp_path,old_priority=1,fresh_priority=95)
    assert _picked_source(store)==2
    # Selection is non-destructive: all other jobs and settings survive.
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE state='QUEUED'").fetchone()[0]==40
        assert con.execute("SELECT min_publish_interval_minutes FROM channels").fetchone()[0]==45


def test_overload_preserves_source_priority_within_same_six_hour_tier(tmp_path):
    store=_seed_backlog(tmp_path,old_priority=2,fresh_priority=95,
                        old_hours=4,fresh_hours=1)
    assert _picked_source(store)==1


def test_small_queue_keeps_priority_first_existing_behavior(tmp_path):
    store=_seed_backlog(tmp_path,old_priority=2,fresh_priority=95,old_count=1)
    assert _picked_source(store)==1


def test_generic_capitalized_words_acronyms_and_roman_numerals_are_not_models():
    assert _protected_latin_tokens("Semantic analysis, ACL, III, Review, Overview")==set()
    assert "gen5" in _protected_latin_tokens("Gen5")


def test_unsupported_model_name_is_still_blocked():
    row={"title":"Місто повідомило про відкриття школи",
         "raw_text":"У Запоріжжі відкрили школу після ремонту"}
    with pytest.raises(FactGuardError,match="Gen5"):
        validate_fact_guard(row,"У Запоріжжі відкрили школу Gen5 після ремонту.")
