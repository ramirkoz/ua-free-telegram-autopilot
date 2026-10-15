"""Safety regressions for Telegram split-text/album stitching (v2.1.15)."""
import json

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.telegram_ingest_policy import stitch_adjacent_telegram_media


def _entry(number, *, text="", media=None, when="2026-10-15T12:00:00+00:00"):
    return TelegramEntry(
        post=f"community/{number}",
        text=text,
        published=when,
        media=list(media or []),
    )


def test_adjacent_text_and_album_with_timestamps_is_stitched():
    entries = [
        _entry(10, text="Рішення громади"),
        _entry(11, media=[encode_media("image", "https://example.test/a.jpg")], when="2026-10-15T12:00:15+00:00"),
        _entry(12, media=[encode_media("image", "https://example.test/b.jpg")], when="2026-10-15T12:00:20+00:00"),
    ]
    articles = stitch_adjacent_telegram_media("community", entries)
    assert len(articles) == 1
    assert len(articles[0].media_urls) == 2
    assert json.loads(articles[0].article_layout_json)["telegram"]["message_ids"] == ["10", "11", "12"]


def test_missing_timestamps_cannot_borrow_neighbouring_media():
    entries = [
        _entry(10, text="Перше повідомлення", when=None),
        _entry(11, media=[encode_media("image", "https://example.test/unrelated.jpg")], when=None),
        _entry(12, text="Друге повідомлення", when=None),
    ]
    articles = stitch_adjacent_telegram_media("community", entries)
    assert [article.raw_text for article in articles] == ["Перше повідомлення", "Друге повідомлення"]
    assert all(not article.media_urls for article in articles)


def test_five_minute_boundary_prevents_media_borrowing():
    articles = stitch_adjacent_telegram_media("community", [
        _entry(20, text="Окреме повідомлення"),
        _entry(21, media=[encode_media("image", "https://example.test/later.jpg")], when="2026-10-15T12:06:00+00:00"),
    ])
    assert len(articles) == 1
    assert not articles[0].media_urls
