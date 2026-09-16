from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle


def _article_with_three_images() -> dict[str, str]:
    return {
        "media_json": '["image:https://example.com/a.jpg", "image:https://example.com/b.jpg", "image:https://example.com/c.jpg"]',
        "article_layout_json": "{}",
        "title": "Test article",
        "raw_text": "Test raw text",
        "final_text": "Test final text",
    }


def test_publisher_uses_publication_media_boundary() -> None:
    source = (Path(__file__).parents[1] / "telegram_autopilot" / "v2" / "publisher.py").read_text(encoding="utf-8")
    assert "build_publication_media_bundle" in source
    assert "bundle = build_publication_media_bundle(channel, article)" in source
    assert "bundle = build_media_bundle(article)" not in source


def test_editorial_publication_bundle_is_single_media(monkeypatch) -> None:
    hero = SimpleNamespace(kind="image", url="https://example.com/b.jpg")
    prepared = SimpleNamespace(telegram_hero=hero)
    monkeypatch.setattr("telegram_autopilot.media_pipeline.prepare_article_media", lambda *args, **kwargs: prepared)

    channel = SimpleNamespace(mode=ChannelMode.EDITORIAL)
    bundle = build_publication_media_bundle(channel, _article_with_three_images())

    assert bundle.count == 1
    assert bundle.items[0].url == "https://example.com/b.jpg"
    assert bundle.source_media_count == 1


def test_monitoring_publication_bundle_preserves_album() -> None:
    channel = SimpleNamespace(mode=ChannelMode.MONITORING)
    bundle = build_publication_media_bundle(channel, _article_with_three_images())

    assert bundle.count == 3
