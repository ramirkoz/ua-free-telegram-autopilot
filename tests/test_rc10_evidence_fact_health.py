from __future__ import annotations

from pathlib import Path

import pytest

from telegram_autopilot.database import Database
from telegram_autopilot.evidence_pack import build_evidence_pack
from telegram_autopilot.fact_guard import FactGuardError, validate_fact_guard
from telegram_autopilot.production_pipeline_rc9 import POST_FORMAT_PREFIX, build_rewrite_prompt
from telegram_autopilot.models import Channel


def article(**overrides):
    base = {
        "title": "Researchers publish a technical update",
        "raw_text": "",
        "source_published_at": "2026-08-18T10:00:00+00:00",
    }
    base.update(overrides)
    return base


def channel() -> Channel:
    return Channel(
        id=1,
        name="Test",
        telegram_chat_id="@test",
        editorial_profile="Technology and science news.",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
        created_at="2026-08-18T00:00:00+00:00",
        updated_at="2026-08-18T00:00:00+00:00",
    )


def test_evidence_pack_keeps_late_fact_bearing_sentence():
    boring = " ".join(
        f"Background sentence {i} describes ordinary context without an important measurement."
        for i in range(1, 24)
    )
    tail = "Meta said Muse Glimmer uses 30 billion parameters and can run on one consumer GPU."
    row = article(title="Meta introduces Muse Glimmer", raw_text=boring + " " + tail)

    pack = build_evidence_pack(row, char_budget=950)

    assert pack.truncated is True
    assert "TITLE: Meta introduces Muse Glimmer" in pack.text
    assert "30 billion parameters" in pack.text
    assert "consumer GPU" in pack.text
    assert len(pack.text) <= 950


def test_prompt_uses_bounded_evidence_pack_not_blind_tail_cut():
    raw = ("This is ordinary context about a research project. " * 180) + (
        "At the end researchers reported 72 percent efficiency with the XG-900 prototype."
    )
    prompt = build_rewrite_prompt(channel(), article(raw_text=raw), local=False, hard_limit=900)
    assert "SOURCE EVIDENCE PACK" in prompt
    assert "72 percent efficiency" in prompt
    assert "XG-900" in prompt
    assert len(prompt) < 7000


def test_fact_guard_allows_sourced_entity_and_superlative():
    row = article(
        title="OpenAI announces first XG-900 test",
        raw_text="OpenAI said this was the first XG-900 field test. The company described the result as preliminary.",
    )
    result = validate_fact_guard(row, "OpenAI провела перший польовий тест XG-900. Результат компанія назвала попереднім.")
    assert result.checked_entities >= 2
    assert result.checked_claims >= 1


def test_fact_guard_blocks_invented_model_or_company():
    row = article(raw_text="Researchers published a new cooling method for data centers.")
    with pytest.raises(FactGuardError, match="немає у джерелі"):
        validate_fact_guard(row, "Nvidia представила систему XG-900 для нового методу охолодження.")


def test_fact_guard_blocks_unsupported_record_claim():
    row = article(raw_text="Researchers reported an efficiency improvement in a laboratory test.")
    with pytest.raises(FactGuardError, match="рекорд"):
        validate_fact_guard(row, "Дослідники повідомили про рекордний результат у лабораторному тесті.")


def test_source_health_and_audit_are_additive_and_secret_safe(tmp_path: Path):
    db = Database(tmp_path / "autopilot.sqlite3")
    cid = db.save_channel(
        channel_id=None,
        name="UA FREE",
        telegram_chat_id="@ua_free",
        editorial_profile="Tech",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
    )
    sid = db.save_source(source_id=None, channel_id=cid, kind="rss", name="Source", url="https://example.com/rss", enabled=True)

    db.source_checked(sid, initialized=True, inserted_count=3, baseline=True)
    first = db.source_health(sid)
    assert first["total_checks"] == 1
    assert first["total_inserted"] == 3
    assert not first["last_new_at"]

    db.source_checked(sid, initialized=True, inserted_count=2, baseline=False)
    db.source_checked(sid, error="HTTP 503")
    health = db.source_health(sid)
    assert health["total_checks"] == 3
    assert health["total_errors"] == 1
    assert health["total_inserted"] == 5
    assert health["last_new_at"]

    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    db.audit("telegram", "error", f"token={token} Authorization: Bearer super-secret-value-123456", channel_id=cid)
    rows = db.recent_audit(cid)
    assert rows
    detail = rows[0]["detail"]
    assert token not in detail
    assert "super-secret-value" not in detail
    assert "REDACTED" in detail


def test_rc10_format_marker_forces_pending_rc9_revalidation():
    assert POST_FORMAT_PREFIX == "telegram-post-v5:"


def test_fact_guard_does_not_block_ordinary_first_quarter_wording():
    row = article(raw_text="The company expects shipments in Q1 2027 after certification.")
    # «першому кварталі» is ordinary calendar wording, not a world-first claim.
    result = validate_fact_guard(row, "Компанія очікує постачання у першому кварталі після сертифікації.")
    assert result.checked_claims == 0


def test_new_articles_still_outrank_due_retries(tmp_path: Path):
    from telegram_autopilot.models import CollectedArticle

    db = Database(tmp_path / "queue.sqlite3")
    cid = db.save_channel(
        channel_id=None, name="UA FREE", telegram_chat_id="@ua_free", editorial_profile="Tech",
        enabled=True, include_source_link=False, poll_interval_minutes=5,
        min_publish_interval_minutes=10, dedupe_window_hours=72, max_age_hours=24,
        max_posts_per_cycle=3,
    )
    sid = db.save_source(source_id=None, channel_id=cid, kind="rss", name="Source", url="https://example.com/rss", enabled=True)
    source = db.list_sources(cid)[0]
    old_id = db.insert_collected(source, CollectedArticle(
        external_id="old", title="Old retry", url="https://example.com/old", raw_text="old body",
        published_at=None, media_urls=(), article_layout_json="",
    ), baseline=False)
    new_id = db.insert_collected(source, CollectedArticle(
        external_id="new", title="Fresh news", url="https://example.com/new", raw_text="new body",
        published_at=None, media_urls=(), article_layout_json="",
    ), baseline=False)
    assert old_id and new_id
    db.update_article(old_id, status="retry", next_retry_at="2000-01-01T00:00:00+00:00")
    pending = db.pending_articles(cid)
    assert [int(row["id"]) for row in pending[:2]] == [new_id, old_id]


def test_retry_limit_is_still_bounded_at_five(tmp_path: Path):
    from telegram_autopilot.models import CollectedArticle

    db = Database(tmp_path / "retry.sqlite3")
    cid = db.save_channel(
        channel_id=None, name="UA FREE", telegram_chat_id="@ua_free", editorial_profile="Tech",
        enabled=True, include_source_link=False, poll_interval_minutes=5,
        min_publish_interval_minutes=10, dedupe_window_hours=72, max_age_hours=24,
        max_posts_per_cycle=3,
    )
    sid = db.save_source(source_id=None, channel_id=cid, kind="rss", name="Source", url="https://example.com/rss", enabled=True)
    source = db.list_sources(cid)[0]
    aid = db.insert_collected(source, CollectedArticle(
        external_id="retry", title="Retry", url="https://example.com/retry", raw_text="body",
        published_at=None, media_urls=(), article_layout_json="",
    ), baseline=False)
    assert aid
    states = [db.schedule_retry(aid, f"failure {i}") for i in range(1, 6)]
    assert states == ["retry", "retry", "retry", "retry", "error"]
    row = db.get_article(aid)
    assert row["status"] == "error"
    assert int(row["retry_count"]) == 5
