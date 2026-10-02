from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from telegram_autopilot.v2.editorial_review import EditorialReviewService
from telegram_autopilot.v2.first_run_import import _selective_import
from telegram_autopilot.v2.migration_repair import repair_polling_baseline
from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed(store: V2Store, *, channel_id: int = 1, source_id: int = 1) -> None:
    now = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,channel_mode,poll_interval_minutes,max_age_hours,
                   min_publish_interval_minutes,publish_24h,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (channel_id, "TEST", "@test", "editorial", 15, 24, 0, 1, now, now),
        )
        con.execute(
            "INSERT INTO channel_policies(channel_id,purpose,audience,updated_at) VALUES(?,?,?,?)",
            (channel_id, "OPERATOR PURPOSE", "OPERATOR AUDIENCE", now),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(?,?,?,?,?,?,?)",
            (source_id, channel_id, "rss", "Operator source", "https://example.com/feed", 1, 77),
        )


def _article(store: V2Store, *, external_id: str, final_text: str = "Готовий текст", stage: str = "WRITTEN", decision: str = "REJECT", error: str = "") -> int:
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(
                   channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                   discovered_at,stage,decision,blocked_by,final_text,last_error_code
               ) VALUES(1,1,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                external_id,
                "Story",
                f"https://example.com/{external_id}",
                f"https://example.com/{external_id}",
                "Raw",
                now_iso(),
                stage,
                decision,
                "TELEGRAM" if error else "NONE",
                final_text,
                error,
            ),
        )
        return int(cur.lastrowid)


def test_human_approve_and_reject_resolve_review_queue(tmp_path):
    store = V2Store(tmp_path / "db.sqlite3")
    _seed(store)
    review = EditorialReviewService(store)
    approved = _article(store, external_id="approve")
    rejected = _article(store, external_id="reject")

    assert {approved, rejected} <= {x.article_id for x in review.candidates(limit=50)}

    review.approve(approved)
    # RC102 keeps human-approved items visible until actual publication or explicit reject.
    assert approved in {x.article_id for x in review.candidates(limit=50)}
    assert approved in {int(x["id"]) for x in store.ready_articles(1, 50)}

    review.reject(rejected, "Ні")
    assert rejected not in {x.article_id for x in review.candidates(limit=50)}
    row = store.get_article(rejected)
    assert row is not None
    assert row["stage"] == "ARCHIVED"
    assert row["decision"] == "REJECT"


def test_unknown_delivery_cannot_be_blindly_approved_or_edited(tmp_path):
    store = V2Store(tmp_path / "db.sqlite3")
    _seed(store)
    review = EditorialReviewService(store)
    article_id = _article(
        store,
        external_id="unknown",
        stage="READY",
        decision="PUBLISH",
        error="TELEGRAM_OUTCOME_UNKNOWN",
    )

    with pytest.raises(ValueError, match="не підтвердив результат"):
        review.approve(article_id)
    with pytest.raises(ValueError, match="не підтвердив результат"):
        review.edit(article_id, "Інший готовий текст")

    row = store.get_article(article_id)
    assert row is not None
    assert row["last_error_code"] == "TELEGRAM_OUTCOME_UNKNOWN"
    assert row["blocked_by"] == "TELEGRAM"


def test_human_approved_ready_is_not_expired_by_source_age(tmp_path):
    store = ReadyBacklogStore(tmp_path / "db.sqlite3")
    _seed(store)
    review = EditorialReviewService(store)
    old = (datetime.now(timezone.utc) - timedelta(days=4)).astimezone().isoformat(timespec="seconds")
    article_id = _article(store, external_id="old-approved")
    with store.connect() as con:
        con.execute("UPDATE articles SET discovered_at=?,source_published_at=? WHERE id=?", (old, old, article_id))
    review.approve(article_id)

    assert store.expire_stale_ready(1, 24) == 0
    row = store.get_article(article_id)
    assert row is not None and row["stage"] == "READY" and row["decision"] == "PUBLISH"


def test_import_preserves_rewrite_editor_action_and_migration_markers(tmp_path):
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    old = V2Store(source)
    _seed(old)
    review = EditorialReviewService(old)
    article_id = _article(old, external_id="import-approved", final_text="Ручний фінальний текст")
    review.edit(article_id, "Ручний фінальний текст після правки")
    with old.connect() as con:
        con.execute(
            "INSERT INTO meta(key,value) VALUES('rc98_commercial_manual_positive_profile_v1','1') ON CONFLICT(key) DO UPDATE SET value='1'"
        )
        con.execute("UPDATE channel_policies SET purpose='DO NOT TOUCH',audience='MY AUDIENCE' WHERE channel_id=1")
        con.execute("UPDATE sources SET enabled=1,priority=77 WHERE id=1")

    counts = _selective_import(source, target)
    imported = V2Store(target)
    row = imported.get_article(article_id)
    assert row is not None
    assert row["final_text"] == "Ручний фінальний текст після правки"
    assert row["stage"] == "READY"
    assert row["decision"] == "PUBLISH"
    assert counts["approved_preserved"] == 1

    with imported.connect() as con:
        action = con.execute("SELECT action FROM editorial_actions WHERE article_id=? ORDER BY id DESC LIMIT 1", (article_id,)).fetchone()
        assert action is not None and action[0] == "edit"
        revision = con.execute("SELECT text FROM rewrite_revisions WHERE article_id=? ORDER BY revision DESC LIMIT 1", (article_id,)).fetchone()
        assert revision is not None and revision[0] == "Ручний фінальний текст після правки"
        marker = con.execute("SELECT value FROM meta WHERE key='rc98_commercial_manual_positive_profile_v1'").fetchone()
        assert marker is not None and marker[0] == "1"
        policy = con.execute("SELECT purpose,audience FROM channel_policies WHERE channel_id=1").fetchone()
        source_row = con.execute("SELECT enabled,priority FROM sources WHERE id=1").fetchone()
        assert tuple(policy) == ("DO NOT TOUCH", "MY AUDIENCE")
        assert tuple(source_row) == (1, 77)

    repair_polling_baseline(imported)
    with imported.connect() as con:
        policy = con.execute("SELECT purpose,audience FROM channel_policies WHERE channel_id=1").fetchone()
        source_row = con.execute("SELECT enabled,priority FROM sources WHERE id=1").fetchone()
        assert tuple(policy) == ("DO NOT TOUCH", "MY AUDIENCE")
        assert tuple(source_row) == (1, 77)


def test_rc101_recovery_code_does_not_clear_final_text():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "telegram_autopilot" / "v2"
    for name in ("ready_backlog.py", "media_recovery.py", "hardened_storage.py", "first_run_import.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "final_text=''" not in text
