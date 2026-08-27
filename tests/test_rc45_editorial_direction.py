from __future__ import annotations

from types import SimpleNamespace

import pytest

from telegram_autopilot.ai_router import AIRouterError, Result
from telegram_autopilot.database import Database
from telegram_autopilot.rc42_policy import install_rc42_policy, serialize_editorial_weights
from telegram_autopilot import rc45_policy as rc45


def channel(*, direction=rc45.DIRECTION_EN_TO_UK, weights=()):
    return SimpleNamespace(
        id=1,
        name="Test channel",
        editorial_profile=(
            "Publish current factual news, research and product releases. "
            "Do not publish evergreen explainers or unrelated politics."
        ),
        editorial_weights_json=serialize_editorial_weights(weights),
        content_direction=direction,
    )


def article(title: str, raw: str, article_id: int = 100):
    return {
        "id": article_id,
        "title": title,
        "raw_text": raw,
        "source_published_at": "2026-08-27T06:00:00+00:00",
        "editorial_category": "",
        "teaser_text": "",
        "event_summary": "",
        "full_article_uk": "",
    }


def test_rc45_direction_defaults_and_ukru_detector():
    assert rc45.content_direction(SimpleNamespace()) == rc45.DIRECTION_EN_TO_UK
    ua = (
        "Компанія повідомила про нову систему штучного інтелекту. "
        "Вона працює локально та не потребує постійного підключення до хмари. "
        "Дослідники кажуть, що модель ще тестують і результати можуть змінитися. "
    ) * 4
    ru = (
        "Компания сообщила о новой системе искусственного интеллекта. "
        "Она работает локально и не требует постоянного подключения к облаку. "
        "Исследователи говорят, что модель еще тестируют и результаты могут измениться. "
    ) * 4
    en = (
        "The company announced a new artificial intelligence system. "
        "Researchers say the model is still being tested and results may change. "
    ) * 5
    assert rc45.looks_ukrainian_or_russian(ua)
    assert rc45.looks_ukrainian_or_russian(ru)
    assert not rc45.looks_ukrainian_or_russian(en)


def test_rc45_category_parser_accepts_common_model_wrappers():
    categories = [
        {"name": "AI Models & Agents", "weight": 60},
        {"name": "Science & Health", "weight": 40},
    ]
    assert rc45._extract_category('{"category":"AI Models & Agents"}', categories) == "AI Models & Agents"
    assert rc45._extract_category("Category: Science & Health", categories) == "Science & Health"
    assert rc45._extract_category("The best fit is AI Models & Agents.", categories) == "AI Models & Agents"
    assert rc45._extract_category("__OTHER__", categories) == "__OTHER__"


def test_rc45_other_is_rejected_instead_of_balance_skipped():
    ch = channel(weights=[{"name": "AI Models & Agents", "weight": 100}])
    reason, category = rc45.balance_reject_reason_rc45(
        ch,
        article("US Senate race shifts after primaries", "A political campaign story."),
        [],
        category="__OTHER__",
    )
    assert reason.startswith("EDITORIAL_FIT_RC45_SKIP")
    assert category == "__OTHER__"


def test_rc45_classifier_outage_propagates_for_retry(monkeypatch):
    ch = channel(weights=[{"name": "AI Models & Agents", "weight": 100}])
    item = article(
        "A company changes its product strategy",
        "The source describes a current event but does not contain the literal category name.",
    )

    def fail(*_args, **_kwargs):
        raise AIRouterError("temporary provider outage")

    monkeypatch.setattr(rc45, "run_ai", fail)
    with pytest.raises(AIRouterError):
        rc45.classify_category_rc45(ch, item, [{"name": "AI Models & Agents", "weight": 100}])


def test_rc45_pre_rewrite_dedupe_catches_gemini_cross_outlet_duplicate():
    current = article(
        "Google announces Gemini 3.5 Transcribe for AI-powered speech-to-text",
        (
            "Google introduced Gemini 3.5 Transcribe for speech recognition. "
            "The model removes filler words, supports more than 85 languages, handles noisy speech and custom vocabulary. "
            "Google says it improves on Chirp 3 and can format transcripts while people speak."
        ),
    )
    recent = [{
        "id": 77,
        "title": "Google launches Gemini 3.5 Transcribe with cleaner audio transcripts",
        "raw_text": (
            "Google launched Gemini 3.5 Transcribe, a speech-to-text model that removes filler words. "
            "It supports more than 85 languages, improves noisy speech recognition and accepts custom vocabulary. "
            "The company positions it as the next step after Chirp 3."
        ),
        "event_summary": "",
        "teaser_text": "",
    }]
    match = rc45._source_event_duplicate(current, recent)
    assert match is not None
    assert match[1] == 77


def test_rc45_pre_rewrite_dedupe_does_not_merge_separate_vendor_events():
    current = article(
        "Nvidia introduces NVHBM memory for NVLink Fusion partners",
        "Nvidia described a custom memory interface for partners building accelerators. Amazon Annapurna Labs is an early partner.",
    )
    recent = [{
        "id": 88,
        "title": "Nvidia reports record quarterly revenue from data centers",
        "raw_text": "Nvidia reported quarterly revenue and profit figures driven by data-center GPU demand.",
        "event_summary": "",
        "teaser_text": "",
    }]
    assert rc45._source_event_duplicate(current, recent) is None


def test_rc45_database_migration_persists_channel_direction(tmp_path):
    install_rc42_policy()
    rc45.install_rc45_policy()
    db = Database(tmp_path / "rc45.sqlite3")
    cid = db.save_channel(
        channel_id=None,
        name="English output",
        telegram_chat_id="@english_output",
        editorial_profile="Current Ukrainian and Russian sources rewritten into native English.",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
    )
    db.set_channel_content_direction(cid, rc45.DIRECTION_UKRU_TO_EN)
    saved = db.get_channel(cid)
    assert saved is not None
    assert saved.content_direction == rc45.DIRECTION_UKRU_TO_EN
    with db.connect() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(channels)")}
    assert "content_direction" in columns


def test_rc45_reverse_decide_returns_english_body(monkeypatch):
    install_rc42_policy()
    rc45.install_rc45_policy()

    body = (
        "A Ukrainian robotics lab has started collecting human motion data to train machines for physical tasks. "
        "Participants repeat ordinary movements while cameras record trajectories and timing.\n\n"
        "The project is still experimental, and the source does not claim that this approach will succeed."
    )

    def fake_route(_prompt, _article, **_kwargs):
        return (
            Result(text=body, provider="gemini", model="test", label="Gemini test"),
            {"body": body, "post": body},
        )

    monkeypatch.setattr(rc45, "_route_english", fake_route)
    ch = channel(direction=rc45.DIRECTION_UKRU_TO_EN, weights=[])
    item = article(
        "Українська лабораторія збирає дані рухів людей для роботів",
        "Українська лабораторія почала збирати відео рухів людей для навчання роботів. Проєкт експериментальний, гарантій успіху немає.",
    )

    from telegram_autopilot import production_pipeline

    result = production_pipeline.decide(ch, item, [], hard_limit=900, format_marker="telegram-post-v28:ukru_to_en:900:850:")
    assert result.decision == "publish"
    assert "Ukrainian robotics lab" in result.telegram_teaser
    assert result.event_key.startswith("telegram-post-v28:ukru_to_en")
