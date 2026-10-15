"""Regression coverage for split Telegram text/photo albums in municipal sources."""
import json

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.telegram_ingest_policy import stitch_adjacent_telegram_media


def _entry(post_id, *, text="", images=(), second=0):
    return TelegramEntry(
        post=f"community/{post_id}",
        text=text,
        published=f"2026-10-15T12:{second // 60:02d}:{second % 60:02d}+00:00",
        media=[encode_media("image", f"https://example.test/{name}.jpg") for name in images],
    )


def test_text_then_separate_album():
    result = stitch_adjacent_telegram_media("community", [
        _entry(100, text="Новина громади"),
        _entry(101, images=("one",), second=10),
        _entry(102, images=("two",), second=20),
    ])
    assert len(result) == 1
    assert len(result[0].media_urls) == 2
    assert json.loads(result[0].article_layout_json)["telegram"]["message_ids"] == ["100", "101", "102"]


def test_album_then_text_with_own_photo_keeps_whole_album():
    result = stitch_adjacent_telegram_media("community", [
        _entry(200, images=("one",), second=0),
        _entry(201, images=("two",), second=10),
        _entry(202, text="Новина громади", images=("three",), second=20),
    ])
    assert len(result) == 1
    assert len(result[0].media_urls) == 3
    assert json.loads(result[0].article_layout_json)["telegram"]["message_ids"] == ["200", "201", "202"]


def test_album_then_text_then_more_media():
    result = stitch_adjacent_telegram_media("community", [
        _entry(300, images=("one",), second=0),
        _entry(301, text="Новина громади", images=("two",), second=10),
        _entry(302, images=("three",), second=20),
    ])
    assert len(result) == 1
    assert len(result[0].media_urls) == 3


def test_separated_messages_not_borrowed():
    result = stitch_adjacent_telegram_media("community", [
        _entry(400, text="Перша новина"),
        _entry(402, images=("unrelated",), second=10),
        _entry(403, text="Друга новина", second=20),
    ])
    assert len(result) == 2
    assert not result[0].media_urls
    assert len(result[1].media_urls) == 1
