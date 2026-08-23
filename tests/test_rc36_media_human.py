from __future__ import annotations

import pytest

from telegram_autopilot.media_pipeline import PreparedMedia
from telegram_autopilot.models import Channel
from telegram_autopilot.rc33_policy import install_rc33_policy
from telegram_autopilot.rc35_source_compat import install_rc35_source_compat
from telegram_autopilot.rc36_policy import install_rc36_policy


def _install() -> None:
    install_rc33_policy()
    install_rc35_source_compat()
    install_rc36_policy()


def test_rc36_featured_image_without_story_metadata_is_rejected() -> None:
    _install()
    from telegram_autopilot import media_pipeline
    item = PreparedMedia(index=0, kind="image", url="https://cdn.example.com/hero-12345.jpg", featured=True, classification="photo")
    assert not media_pipeline._semantic_media_match(
        item,
        title="Microsoft links Windows 11 crashes to RGB software",
        article_text="Microsoft says RGB utilities can trigger Windows 11 game crashes.",
    )


def test_rc36_cache_marker_is_v21() -> None:
    _install()
    from telegram_autopilot import production_pipeline, service
    assert production_pipeline.POST_FORMAT_PREFIX == "telegram-post-v21:"
    assert service.POST_FORMAT_PREFIX == "telegram-post-v21:"


def test_rc36_text_mode_is_rejected_before_ai() -> None:
    _install()
    from telegram_autopilot import production_pipeline
    channel = Channel(
        id=1, name="CTRL+UA", telegram_chat_id="@ctrlua", editorial_profile="Technology news",
        enabled=True, include_source_link=True, poll_interval_minutes=5, min_publish_interval_minutes=10,
        dedupe_window_hours=72, max_age_hours=24, max_posts_per_cycle=3, created_at="", updated_at="",
    )
    article = {"title": "Story without media", "raw_text": "A normal English technology story."}
    result = production_pipeline.decide(channel, article, [], hard_limit=4000, format_marker="telegram-post-v21:4096:4000:")
    assert result.decision == "reject"
    assert result.model == "rc36-media-required"
    assert "SKIP_NO_MEDIA" in result.reason


def test_rc36_text_send_is_disabled() -> None:
    _install()
    from telegram_autopilot import service
    with pytest.raises(service.TelegramError) as exc:
        service.send_text("token", "@ctrlua", "body")
    assert exc.value.retryable is False
    assert "SKIP_NO_MEDIA" in str(exc.value)
