from __future__ import annotations

import json
from types import SimpleNamespace

import telegram_autopilot.media_pipeline as legacy_media_pipeline
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle


def _editorial_channel():
    return SimpleNamespace(mode=ChannelMode.EDITORIAL)


def test_editorial_media_does_not_fallback_to_unvalidated_first_url(monkeypatch) -> None:
    """A validator miss must produce a text post, not publish raw media blindly."""

    monkeypatch.setattr(
        legacy_media_pipeline,
        "prepare_article_media",
        lambda *_args, **_kwargs: SimpleNamespace(telegram_hero=None),
    )
    article = {
        "title": "Розмови з ChatGPT читають люди",
        "raw_text": "OpenAI використовує підрядників для перевірки чатів.",
        "final_text": "",
        "media_json": json.dumps(["https://cdn.example/opaque-12345.jpg"]),
        "article_layout_json": "{}",
    }

    bundle = build_publication_media_bundle(_editorial_channel(), article)

    assert bundle.count == 0
    assert bundle.items == ()


def test_editorial_media_keeps_validator_selected_hero(monkeypatch) -> None:
    hero_url = "https://cdn.example/project-lily-report.jpg"
    monkeypatch.setattr(
        legacy_media_pipeline,
        "prepare_article_media",
        lambda *_args, **_kwargs: SimpleNamespace(
            telegram_hero=SimpleNamespace(kind="image", url=hero_url)
        ),
    )
    article = {
        "title": "Project Lily",
        "raw_text": "Дослідження про перевірку розмов користувачів.",
        "final_text": "",
        "media_json": json.dumps([hero_url]),
        "article_layout_json": "{}",
    }

    bundle = build_publication_media_bundle(_editorial_channel(), article)

    assert bundle.count == 1
    assert bundle.items[0].url == hero_url
