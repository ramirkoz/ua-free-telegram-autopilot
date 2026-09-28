from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.editorial_review import EditorialReviewService
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_store(tmp_path) -> tuple[V2Store, EditorialReviewService]:
    store = V2Store(tmp_path / "autopilot-v2.db")
    now = now_iso()
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(1,'EDITORIAL','', 'editorial',?,?)",
            (now, now),
        )
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(2,'MONITORING','', 'monitoring',?,?)",
            (now, now),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','Editorial source','https://example.com/editorial')"
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url) VALUES(2,2,'telegram','Monitoring source','https://t.me/example')"
        )
    review = EditorialReviewService(store)
    review.ensure_schema()
    return store, review


def _article(
    store: V2Store,
    *,
    channel_id: int,
    source_id: int,
    external_id: str,
    final_text: str,
    stage: str,
    decision: str,
    blocked_by: str = "NONE",
    discovered_at: str | None = None,
) -> int:
    discovered = discovered_at or now_iso()
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(
                   channel_id,source_id,external_id,title,source_url,raw_text,discovered_at,
                   stage,decision,blocked_by,final_text
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                channel_id,
                source_id,
                external_id,
                f"Story {external_id}",
                f"https://example.com/{external_id}",
                f"Raw {external_id}",
                discovered,
                stage,
                decision,
                blocked_by,
                final_text,
            ),
        )
        return int(cur.lastrowid)


def test_every_rewritten_non_published_material_is_reviewable(tmp_path):
    store, review = _seed_store(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=10)).astimezone().isoformat(timespec="seconds")

    editorial_reject = _article(
        store,
        channel_id=1,
        source_id=1,
        external_id="editorial-reject",
        final_text="Готовий рерайт editorial.",
        stage="ARCHIVED",
        decision="REJECT",
    )
    monitoring_reject = _article(
        store,
        channel_id=2,
        source_id=2,
        external_id="monitoring-reject",
        final_text="Готовий рерайт monitoring.",
        stage="ARCHIVED",
        decision="REJECT",
    )
    semantic_duplicate = _article(
        store,
        channel_id=2,
        source_id=2,
        external_id="duplicate",
        final_text="Готовий рерайт дубля події.",
        stage="WRITTEN",
        decision="DUPLICATE",
    )
    old_quality_blocked = _article(
        store,
        channel_id=1,
        source_id=1,
        external_id="old-quality",
        final_text="Старий, але готовий рерайт.",
        stage="WRITTEN",
        decision="PUBLISH",
        blocked_by="QUALITY",
        discovered_at=old,
    )

    ids = {item.article_id for item in review.candidates(limit=50)}
    assert {editorial_reject, monitoring_reject, semantic_duplicate, old_quality_blocked} <= ids


def test_published_or_not_rewritten_material_is_not_reviewable(tmp_path):
    store, review = _seed_store(tmp_path)
    published = _article(
        store,
        channel_id=1,
        source_id=1,
        external_id="published",
        final_text="Вже в ефірі.",
        stage="PUBLISHED",
        decision="PUBLISH",
    )
    no_rewrite = _article(
        store,
        channel_id=1,
        source_id=1,
        external_id="no-rewrite",
        final_text="",
        stage="ARCHIVED",
        decision="REJECT",
    )

    ids = {item.article_id for item in review.candidates(limit=50)}
    assert published not in ids
    assert no_rewrite not in ids


def test_explicit_human_reject_resolves_queue_item(tmp_path):
    store, review = _seed_store(tmp_path)
    article_id = _article(
        store,
        channel_id=2,
        source_id=2,
        external_id="manual-reject",
        final_text="Готовий рерайт для ручного рішення.",
        stage="WRITTEN",
        decision="REJECT",
    )

    assert article_id in {item.article_id for item in review.candidates(limit=50)}
    review.reject(article_id, "Редактор остаточно відхилив")
    assert article_id not in {item.article_id for item in review.candidates(limit=50)}
