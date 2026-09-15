from __future__ import annotations

import json

import pytest

from telegram_autopilot.v2.community_context import (
    attribution_for_article,
    community_body_hard_limit,
    community_footer_label,
    community_source_name,
)
from telegram_autopilot.v2.domain import ChannelConfig
from telegram_autopilot.v2.editorial import validate_writer_output
from telegram_autopilot.v2.telegram_attribution import (
    _attribution_entities,
    build_attributed_post_text,
)


def _communities_channel() -> ChannelConfig:
    return ChannelConfig(
        id=3,
        name="ЗАПОРІЖЖЯ | ГРОМАДИ",
        telegram_chat_id="@communities_test",
    )


def test_configured_source_name_becomes_community_context() -> None:
    channel = _communities_channel()
    article = {"source_name": "  Кушугумська   громада  "}

    assert community_source_name(channel, article) == "Кушугумська громада"
    assert community_footer_label(channel, article) == "Читати у «Кушугумська громада»"
    assert community_body_hard_limit(channel, article) < 880


def test_non_communities_channel_does_not_force_source_name_into_body() -> None:
    channel = ChannelConfig(id=1, name="CTRL+UA", telegram_chat_id="@ctrlua_test")
    article = {"source_name": "The Verge"}

    assert community_source_name(channel, article) == ""
    assert community_footer_label(channel, article) == ""
    assert community_body_hard_limit(channel, article) == 880


def test_community_footer_uses_exact_original_post_only() -> None:
    channel = _communities_channel()
    article = {"source_name": "Кушугумська громада"}
    original = "https://t.me/kushugum_hromada/123"
    evidence = "https://example.org/background"

    urls, labels = attribution_for_article(
        channel,
        article,
        source_url=original,
        source_urls=[original, evidence],
    )

    assert urls == [original]
    assert labels == ["Читати у «Кушугумська громада»"]

    post = build_attributed_post_text(
        "Кушугумська громада повідомила мешканцям про нову можливість долучитися до життя громади.",
        source_url=original,
        source_urls=urls,
        source_labels=labels,
        include_source_link=True,
        hard_limit=900,
    )
    assert post.endswith("Читати у «Кушугумська громада»")
    assert "\n\nДжерело" not in post

    entities = json.loads(_attribution_entities(post, original, urls, labels))
    links = [item for item in entities if item.get("type") == "text_link"]
    assert len(links) == 1
    assert links[0]["url"] == original
    assert links[0]["length"] == len("Читати у «Кушугумська громада»")


def test_writer_qa_rejects_contextless_community_rewrite() -> None:
    article = {
        "source_name": "Кушугумська громада",
        "title": "Як мешканці можуть долучатися до життя громади",
        "raw_text": (
            "Мешканців громади закликають брати участь в опитуваннях, пропонувати власні ідеї, "
            "поширювати важливу інформацію та підтримувати громадські й волонтерські ініціативи."
        ),
    }
    contextless = (
        "Мешканців громади закликають долучатися до її життя: брати участь в опитуваннях, "
        "пропонувати власні ідеї, поширювати важливу інформацію та підтримувати волонтерські ініціативи."
    )

    with pytest.raises(ValueError, match="втрачено назву громади"):
        validate_writer_output(
            article,
            contextless,
            min_chars=80,
            max_chars=450,
            hard_max_chars=850,
            required_context="Кушугумська громада",
        )


def test_writer_qa_accepts_explicit_configured_community_name() -> None:
    article = {
        "source_name": "Кушугумська громада",
        "title": "Як мешканці можуть долучатися до життя громади",
        "raw_text": (
            "Мешканців громади закликають брати участь в опитуваннях, пропонувати власні ідеї, "
            "поширювати важливу інформацію та підтримувати громадські й волонтерські ініціативи."
        ),
    }
    text = (
        "Кушугумська громада закликає мешканців долучатися до її життя: брати участь в опитуваннях, "
        "пропонувати власні ідеї, поширювати важливу інформацію та підтримувати волонтерські ініціативи."
    )

    assert validate_writer_output(
        article,
        text,
        min_chars=80,
        max_chars=450,
        hard_max_chars=850,
        required_context="Кушугумська громада",
    ) == text


def test_other_channels_keep_generic_attribution_contract() -> None:
    channel = ChannelConfig(id=1, name="CTRL+UA", telegram_chat_id="@ctrlua_test")
    article = {"source_name": "The Verge"}
    primary = "https://example.org/story"
    extra = "https://example.net/evidence"

    urls, labels = attribution_for_article(
        channel,
        article,
        source_url=primary,
        source_urls=[primary, extra],
    )
    assert urls == [primary, extra]
    assert labels is None

    post = build_attributed_post_text(
        "Це достатньо довгий тестовий текст українською для перевірки незміненої атрибуції інших каналів.",
        source_url=primary,
        source_urls=urls,
        source_labels=labels,
        include_source_link=True,
        hard_limit=900,
    )
    assert post.endswith("Джерело 1\nДжерело 2")
