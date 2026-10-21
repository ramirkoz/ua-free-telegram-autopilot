"""2.2.12: never burn scarce publishing slots rescuing unpublishable stale news.

Regression scope: conservative capacity estimate, FIFO rescue when uncongested,
freshness under real overload, read-only receipt fingerprint. No Telegram calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.capacity_pressure import capacity_window
from telegram_autopilot.v2.delivery_integrity import delivery_integrity_snapshot
from telegram_autopilot.v2.storage import V2Store, now_iso


def _capacity(n: int, gap: int = 45):
    return capacity_window(
        pending_jobs=n,
        min_interval_minutes=gap,
        publish_24h=False,
        publish_start="08:00",
        publish_end="20:00",
        max_age_hours=24,
    )


def test_capacity_matches_45_minute_window_and_111_backlog():
    report = _capacity(111)
    assert report["publish_slots_before_ttl_estimate"] == 16
    assert report["overloaded"] is True
    assert report["pending_selection"] == "FRESHNESS_FIRST"
    assert report["preserves_operator_interval"] is True


def test_other_channel_without_overload_keeps_rescue():
    small = _capacity(3)
    assert small["overloaded"] is False
    assert small["pending_selection"] == "RESCUE_NEAR_TTL"
    monitoring = capacity_window(
        pending_jobs=11, min_interval_minutes=5, publish_24h=True,
        publish_start="07:00", publish_end="00:00", max_age_hours=24,
    )
    assert monitoring["overloaded"] is False


def test_unknown_schedule_stays_conservative():
    fallback = capacity_window(
        pending_jobs=35, min_interval_minutes=45, publish_24h=False,
        publish_start="unreadable", publish_end="value", max_age_hours=24,
    )
    assert not fallback["overloaded"]


def _seed_store(tmp_path, *, old_count: int):
    store = V2Store(tmp_path / "operator.sqlite3")
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,enabled,min_publish_interval_minutes,
                   publish_24h,publish_start,publish_end,max_age_hours,
                   created_at,updated_at
               ) VALUES(1,'CTRL','',1,45,0,'08:00','20:00',24,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority)
               VALUES(1,1,'rss','Example','https://example.org/rss',1,1,10)"""
        )
        for i in range(old_count + 1):
            published = (datetime.now(timezone.utc) - timedelta(hours=21 if i < old_count else 1)).isoformat()
            cur = con.execute(
                """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,
                   canonical_source_url,raw_text,source_published_at,discovered_at,stage,decision)
                   VALUES(1,1,?,?,?,?,?,?,?,'COLLECTED','PENDING')""",
                (str(i), f"news-{i}", f"https://example.org/{i}",
                 f"https://example.org/{i}", f"news-{i}", published, stamp),
            )
            article_id = int(cur.lastrowid)
            con.execute(
                """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,
                   available_at,created_at,updated_at)
                   VALUES(?,1,'process','QUEUED',10,?,?,?)""",
                (article_id, stamp, stamp, stamp),
            )
    return store


def test_overloaded_claim_prefers_recent_source(tmp_path):
    # 40 near-TTL jobs plus one fresh candidate, all same source priority.
    store = _seed_store(tmp_path, old_count=40)
    job = store.claim_job(channel_id=1, worker_id="test")
    assert job is not None
    with store.connect() as con:
        row = con.execute("SELECT external_id FROM articles WHERE id=?", (job["article_id"],)).fetchone()
    assert row["external_id"] == "40"
    # Read-only selection must not purge or rewrite the remaining work.
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE state='QUEUED'").fetchone()[0] == 40


def test_under_capacity_claim_retains_old_rescue(tmp_path):
    store = _seed_store(tmp_path, old_count=1)
    job = store.claim_job(channel_id=1, worker_id="test")
    with store.connect() as con:
        row = con.execute("SELECT external_id FROM articles WHERE id=?", (job["article_id"],)).fetchone()
    assert row["external_id"] == "0"


def test_delivery_integrity_digest_stable_and_sensitive_to_new_receipt(tmp_path):
    store = _seed_store(tmp_path, old_count=1)
    with store.connect() as con:
        con.execute(
            """INSERT INTO publication_delivery_journal(
                article_id,channel_id,state,primary_message_id,committed_at,updated_at)
               VALUES(1,1,'COMMITTED','810','2026-10-21T10:00:00+03:00',?)""",
            (now_iso(),),
        )
    before = delivery_integrity_snapshot(store)
    assert before["committed_count"] == 1
    assert before["auto_replay"] is False
    assert before["auto_restore"] is False
    assert before == delivery_integrity_snapshot(store)
    with store.connect() as con:
        con.execute(
            """INSERT INTO publication_delivery_journal(
                article_id,channel_id,state,primary_message_id,committed_at,updated_at)
               VALUES(2,1,'COMMITTED','811','2026-10-21T10:10:00+03:00',?)""",
            (now_iso(),),
        )
    after = delivery_integrity_snapshot(store)
    assert after["committed_count"] == 2
    assert after["committed_receipts_sha256"] != before["committed_receipts_sha256"]
