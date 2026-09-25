from __future__ import annotations

import json
import sqlite3

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, SourceAttributionMode
from telegram_autopilot.v2.editorial import validate_writer_output
from telegram_autopilot.v2.source_attribution import (
    attribution_for_article,
    source_body_hard_limit,
    source_context_name,
    source_footer_label,
)
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.telegram_attribution import _attribution_entities, build_attributed_post_text


def _named_channel(name: str = "ЗАПОРІЖЖЯ | ГРОМАДИ") -> ChannelConfig:
    return ChannelConfig(
        id=3,
        name=name,
        telegram_chat_id="@named_source_test",
        mode=ChannelMode.MONITORING,
        source_attribution_mode=SourceAttributionMode.NAMED_SOURCE,
    )


def test_channel_name_alone_no_longer_enables_named_attribution() -> None:
    channel = ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test")
    article = {"source_name": "Кушугумська громада"}
    assert source_context_name(channel, article) == ""
    assert source_footer_label(channel, article) == ""
    assert source_body_hard_limit(channel, article) == 880


def test_explicit_named_source_mode_is_generic_not_community_specific() -> None:
    channel = _named_channel("МОНІТОРИНГ ОФІЦІЙНИХ ДЖЕРЕЛ")
    article = {"source_name": "Міністерство цифрової трансформації"}
    assert source_context_name(channel, article) == "Міністерство цифрової трансформації"
    assert source_footer_label(channel, article) == "Читати у «Міністерство цифрової трансформації»"
    assert source_body_hard_limit(channel, article) < 880


def test_named_footer_uses_exact_primary_original_post_only() -> None:
    channel = _named_channel()
    article = {"source_name": "Кушугумська громада"}
    original = "https://t.me/kushugum_hromada/123"
    evidence = "https://example.org/background"
    urls, labels = attribution_for_article(channel, article, source_url=original, source_urls=[original, evidence])
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


def test_standard_mode_keeps_generic_attribution_even_for_communities_name() -> None:
    channel = ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test")
    article = {"source_name": "Кушугумська громада"}
    primary = "https://example.org/story"
    extra = "https://example.net/evidence"
    urls, labels = attribution_for_article(channel, article, source_url=primary, source_urls=[primary, extra])
    assert urls == [primary, extra]
    assert labels is None
    post = build_attributed_post_text(
        "Це достатньо довгий тестовий текст українською для перевірки стандартної атрибуції каналу.",
        source_url=primary,
        source_urls=urls,
        source_labels=labels,
        include_source_link=True,
        hard_limit=900,
    )
    assert post.endswith("Джерело 1\nДжерело 2")


def test_writer_qa_requires_explicit_named_source_context_when_requested() -> None:
    article = {
        "source_name": "Кушугумська громада",
        "title": "Як мешканці можуть долучатися до життя громади",
        "raw_text": "Мешканців громади закликають брати участь в опитуваннях, пропонувати власні ідеї та підтримувати волонтерські ініціативи.",
    }
    contextless = "Мешканців громади закликають долучатися до її життя: брати участь в опитуваннях, пропонувати власні ідеї та підтримувати волонтерські ініціативи."
    with pytest.raises(ValueError, match="втрачено назву джерела"):
        validate_writer_output(article, contextless, min_chars=80, max_chars=450, hard_max_chars=850, required_context="Кушугумська громада")


def test_source_attribution_schema_upgrade_is_explicit_and_name_agnostic(tmp_path) -> None:
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        con.execute("CREATE TABLE channels (id INTEGER PRIMARY KEY,name TEXT NOT NULL,channel_mode TEXT NOT NULL DEFAULT 'editorial')")
        con.execute("INSERT INTO channels(id,name,channel_mode) VALUES(3,'ЗАПОРІЖЖЯ | ГРОМАДИ','monitoring')")
    V2Store(db)
    with sqlite3.connect(db) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(channels)")}
        mode = con.execute("SELECT source_attribution_mode FROM channels WHERE id=3").fetchone()[0]
        marker = con.execute("SELECT value FROM meta WHERE key='rc62_source_attribution_explicit_v1'").fetchone()[0]
    assert "source_attribution_mode" in columns
    assert mode == "standard"
    assert marker == "1"
