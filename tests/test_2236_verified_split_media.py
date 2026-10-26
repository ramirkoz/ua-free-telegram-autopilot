"""Regression gates for 2.2.36 verified Telegram split-media recovery."""
from __future__ import annotations

import json
from types import SimpleNamespace

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2 import strict_ingest as strict
from telegram_autopilot.v2.ingest import TelegramEntry


def _entry(n, text="", media=(), reply=""):
    return TelegramEntry(
        post=f"community/{n}", text=text, published="2026-10-26T11:00:00+00:00",
        media=list(media), reply_to_post=reply,
    )


def test_relative_absolute_and_root_reply_links_only_same_source():
    assert strict._verified_reply_post_236("community", "/community/40") == "community/40"
    assert strict._verified_reply_post_236("community", "https://t.me/community/40") == "community/40"
    assert strict._verified_reply_post_236("community", "https://t.me/s/community/40?single") == "community/40"
    assert strict._verified_reply_post_236("community", "40") == "community/40"
    assert strict._verified_reply_post_236("community", "https://t.me/unrelated/40") == ""
    assert strict._verified_reply_post_236("community", "https://evil.test/community/40") == ""
    assert strict._verified_reply_post_236("community", "/community/0") == ""


def test_reply_markup_links_owner_without_borrowing_reply_thumbnail():
    parser = strict.StrictTelegramParser("community")
    parser.feed('<div class="tgme_widget_message" data-post="community/41">'
                '<a class="tgme_widget_message_reply" href="/community/40">Відповідь</a>'
                '<div class="tgme_widget_message_text">Повідомлення громади.</div></div>')
    parser.close()
    assert len(parser.entries) == 1
    assert parser.entries[0].reply_to_post == "community/40"


def test_root_reply_is_attached_to_exact_current_post():
    parser = strict.StrictTelegramParser("community")
    parser.feed('<div class="tgme_widget_message" data-post="community/40">'
                '<div class="tgme_widget_message_text">Перше повідомлення.</div></div>'
                '<div class="tgme_widget_message" data-post="community/41" data-reply-to="40">'
                '<div class="tgme_widget_message_text">Друге повідомлення.</div></div>')
    parser.close()
    assert parser.entries[0].reply_to_post == ""
    assert parser.entries[1].reply_to_post == "community/40"


def _run_collector(monkeypatch, *, first, exact):
    urls = []
    class FakeParser:
        def __init__(self, username):
            self.entries = []
        def feed(self, text):
            self.entries = list(first if text == "LIST" else exact)
        def close(self): pass
    def fetch(url, **kwargs):
        urls.append(url)
        return SimpleNamespace(body=b"LIST" if "/s/" in url else b"EXACT")
    monkeypatch.setattr(strict.collector, "_telegram_username", lambda url: "community")
    monkeypatch.setattr(strict.collector, "_source_fetch", fetch)
    monkeypatch.setattr(strict, "StrictTelegramParser", FakeParser)
    monkeypatch.setattr(strict, "_hydrate_exact_video_post", lambda user, entry: entry)
    result = strict.collect_telegram_strict(SimpleNamespace(url="https://t.me/community"))
    return result, urls


def test_source_photo_link_fetches_exact_omitted_media(monkeypatch):
    photo = encode_media("image", "https://media.example.test/exact.jpg")
    posts, urls = _run_collector(monkeypatch,
        first=[_entry(41, "Світлини: https://t.me/community/40")],
        exact=[_entry(40, media=[photo])])
    assert len(urls) == 2
    assert len(posts) == 1
    assert posts[0].media_urls == [photo]
    layout = json.loads(posts[0].article_layout_json)
    assert layout["telegram"]["message_ids"] == ["40", "41"]
    assert layout["telegram"]["stitch_policy"] == "explicit_reply_group_or_source_link_v236"


def test_explicit_reply_without_media_url_can_fetch_exact_photo(monkeypatch):
    photo = encode_media("image", "https://media.example.test/real.jpg")
    posts, urls = _run_collector(monkeypatch,
        first=[_entry(41, "Текст про навчання.", reply="community/40")],
        exact=[_entry(40, media=[photo])])
    assert posts[0].media_urls == [photo]
    assert len(urls) == 2


def test_unlinked_adjacent_photo_never_becomes_the_texts_photo(monkeypatch):
    photo = encode_media("image", "https://media.example.test/unrelated.jpg")
    posts, urls = _run_collector(monkeypatch,
        first=[_entry(40, media=[photo]), _entry(41, "Текст про іншу новину.")],
        exact=[])
    assert len(urls) == 1
    assert len(posts) == 1
    assert posts[0].media_urls == []


def test_mismatched_exact_post_never_supplies_photo(monkeypatch):
    photo = encode_media("image", "https://media.example.test/wrong.jpg")
    posts, urls = _run_collector(monkeypatch,
        first=[_entry(41, "Фото: https://t.me/community/40")],
        exact=[_entry(999, media=[photo])])
    assert posts[0].media_urls == []
    assert len(urls) == 2


def test_conflicting_owners_must_not_duplicate_an_image():
    photo = encode_media("image", "https://media.example.test/unique.jpg")
    posts = strict.strict_stitch_telegram("community", [
        _entry(40, media=[photo]),
        _entry(41, "Фото: https://t.me/community/40"),
        _entry(42, "Інше фото: https://t.me/community/40"),
    ])
    assert all(photo not in post.media_urls for post in posts)


def test_foreign_channel_and_unrelated_web_link_do_not_trigger_exact_fetch(monkeypatch):
    posts, urls = _run_collector(monkeypatch,
        first=[_entry(41, "Фото: https://t.me/other_channel/40"), _entry(42, "https://example.org/another/23")],
        exact=[])
    assert len(urls) == 1
    assert len(posts) == 2
