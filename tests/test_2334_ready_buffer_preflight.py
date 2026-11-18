"""2.3.34: READY holds may retire only provably ineligible pending work.

No AI, Telegram or production Data are used. This is deliberately a SQLite
test with the same source/restart fence as the operator's process worker.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.domain import Stage, Decision
from telegram_autopilot.v2.editorial_state import ensure_editorial_state_schema
from telegram_autopilot.v2.runtime import ChannelRuntimeState, RuntimeEngine
from telegram_autopilot.v2.storage import V2Store


KYIV = timezone(timedelta(hours=2))
NOW = datetime(2026, 11, 16, 9, 2, tzinfo=KYIV)
START = "2026-11-16T08:52:33+02:00"
CHECKPOINT = "2026-11-16T08:45:00+02:00"
OLD = "2026-11-15T19:15:00+02:00"
SAME_DAY = "2026-11-16T08:30:00+02:00"
AFTER_START = "2026-11-16T08:57:00+02:00"


def _store(tmp_path):
    store = V2Store(tmp_path / "candidate_2334.sqlite3")
    ensure_editorial_state_schema(store)
    stamp = NOW.isoformat()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                 id,name,telegram_chat_id,enabled,channel_mode,
                 min_publish_interval_minutes,max_age_hours,created_at,updated_at
               ) VALUES(1,'CTRL+UA','',1,'editorial',30,24,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            """INSERT INTO channels(
                 id,name,telegram_chat_id,enabled,channel_mode,
                 min_publish_interval_minutes,max_age_hours,created_at,updated_at
               ) VALUES(3,'ГРОМАДИ','',1,'monitoring',5,24,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,last_checked_at)
               VALUES(10,1,'rss','Example','https://example.org/feed',1,1,?)""",
            (CHECKPOINT,),
        )
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,last_checked_at)
               VALUES(30,3,'telegram','Example GR','https://example.org/gr',1,1,?)""",
            (CHECKPOINT,),
        )
    return store


def _queue(store, key, source_at, discovered_at, *,
           cid=1, blocked_by="NONE", human=False, journal=False):
    stamp = NOW.isoformat()
    source_id = 10 if cid == 1 else 30
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(
                 channel_id,source_id,external_id,title,source_url,
                 canonical_source_url,raw_text,source_published_at,
                 discovered_at,stage,decision,blocked_by
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, source_id, key, key, "https://example.org/" + key,
             "https://example.org/" + key, "Article body about " + key,
             source_at, discovered_at, "COLLECTED", "PENDING", blocked_by),
        )
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO jobs(
                 article_id,channel_id,job_type,state,priority,
                 available_at,created_at,updated_at
               ) VALUES(?,?,'process','QUEUED',10,?,?,?)""",
            (aid, cid, stamp, stamp, stamp),
        )
        if human:
            con.execute(
                """INSERT INTO editorial_actions(article_id,channel_id,action,created_at)
                   VALUES(?,?,'approve',?)""", (aid, cid, stamp),
            )
        if journal:
            con.execute(
                """INSERT INTO publication_delivery_journal(
                     article_id,channel_id,state,updated_at
                   ) VALUES(?,?,'UNKNOWN',?)""",
                (aid, cid, stamp),
            )
    return aid


def _engine(store):
    # Construct only the fields consumed by this source-only preflight.
    engine = object.__new__(RuntimeEngine)
    engine.store = store
    engine.started_at = START
    engine.restart_checkpoints_260 = {"10": CHECKPOINT, "30": CHECKPOINT}
    engine.stop_event = threading.Event()
    return engine


def test_ready_hold_prunes_only_the_prior_restart_rejections(tmp_path):
    store = _store(tmp_path)
    stale = _queue(store, "old-before-boot", OLD, "2026-11-15T19:20:00+02:00")
    unknown = _queue(store, "receipt-unknown", OLD, "2026-11-15T19:20:00+02:00", journal=True)
    human = _queue(store, "approved-by-human", OLD, "2026-11-15T19:20:00+02:00", human=True)
    same_day = _queue(store, "source-checkpoint-continuity", SAME_DAY, "2026-11-16T08:33:00+02:00")
    fresh = _queue(store, "postboot-new", AFTER_START, "2026-11-16T08:58:00+02:00")
    blocked = _queue(store, "quality-retry", OLD, "2026-11-15T19:20:00+02:00", blocked_by="QUALITY")
    regional = _queue(store, "regional-unrelated", OLD, "2026-11-15T19:20:00+02:00", cid=3)

    state = ChannelRuntimeState(channel_id=1)
    engine = _engine(store)
    assert engine._retire_restart_ineligible_2334(1, state, limit=48, now=NOW) == 1
    with store.connect() as con:
        for aid, expected in ((stale, "REJECT"), (unknown, "PENDING"),
                              (human, "PENDING"), (same_day, "PENDING"),
                              (fresh, "PENDING"), (blocked, "PENDING"),
                              (regional, "PENDING")):
            row = con.execute("SELECT decision FROM articles WHERE id=?", (aid,)).fetchone()
            assert row["decision"] == expected
        assert con.execute(
            "SELECT state FROM jobs WHERE article_id=?", (stale,)
        ).fetchone()["state"] == "DONE"
        assert con.execute(
            "SELECT state FROM publication_delivery_journal WHERE article_id=?", (unknown,)
        ).fetchone()["state"] == "UNKNOWN"
        assert con.execute(
            "SELECT min_publish_interval_minutes FROM channels WHERE id=1"
        ).fetchone()[0] == 30
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE state='QUEUED'").fetchone()[0] == 6
    assert state.processed == 1 and state.jobs_rejected == 1
    assert engine._retire_restart_ineligible_2334(3, ChannelRuntimeState(channel_id=3), now=NOW) == 0
    assert engine._retire_restart_ineligible_2334(1, state, now=NOW) == 0


def test_stopped_runtime_never_trims_pending_jobs(tmp_path):
    store = _store(tmp_path)
    aid = _queue(store, "old", OLD, "2026-11-15T19:20:00+02:00")
    engine = _engine(store)
    engine.stop_event.set()
    assert engine._retire_restart_ineligible_2334(1, ChannelRuntimeState(channel_id=1), now=NOW) == 0
    assert store.get_article(aid)["decision"] == str(Decision.PENDING)


def test_source_date_missing_fails_closed_but_no_missing_owner_actions(tmp_path):
    store = _store(tmp_path)
    aid = _queue(store, "undated", "", "2026-11-16T08:58:00+02:00")
    state = ChannelRuntimeState(channel_id=1)
    assert _engine(store)._retire_restart_ineligible_2334(1, state, now=NOW) == 1
    assert store.get_article(aid)["stage"] == str(Stage.ARCHIVED)
