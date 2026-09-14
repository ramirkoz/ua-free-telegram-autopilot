from __future__ import annotations

import json

from telegram_autopilot.media import decode_media
from telegram_autopilot.telegram import _safe_text_entities
from telegram_autopilot.v2.strict_ingest import StrictTelegramParser, strict_stitch_telegram


def _urls(entry) -> list[str]:
    out = []
    for encoded in entry.media:
        _kind, url = decode_media(encoded)
        out.append(url)
    return out


def test_cve_and_dotted_build_are_explicit_code_entities_not_phone_autolinks() -> None:
    text = (
        "Уразливість CVE-2026-51990 використовується проти Chromium 80. "
        "Tencent виправила це у версії 16.3.0.3498.\n\nДжерело"
    )
    raw = _safe_text_entities(text, "https://example.com/story")
    entities = json.loads(raw)
    code = [item for item in entities if item["type"] == "code"]
    links = [item for item in entities if item["type"] == "text_link"]
    assert len(code) == 2
    assert len(links) == 1
    assert links[0]["url"] == "https://example.com/story"
    # No invisible-character workaround: copied text stays byte-for-byte identical.
    assert "\u200b" not in text and "\u2060" not in text


def test_real_phone_number_is_not_forced_into_code_entity() -> None:
    text = "Телефон громади: +380 50 123 45 67\n\nДжерело"
    entities = json.loads(_safe_text_entities(text, "https://example.com"))
    assert [item["type"] for item in entities] == ["text_link"]


def test_exact_post_link_preview_becomes_single_fallback_when_direct_media_missing() -> None:
    html = """
    <div class="tgme_widget_message" data-post="community/200">
      <a class="tgme_widget_message_user_photo"><img src="https://cdn.example/avatar.jpg"></a>
      <a class="tgme_widget_message_link_preview" href="https://example.gov.ua/news/200">
        <i class="link_preview_image" style="background-image:url('https://cdn.example/preview.jpg')"></i>
      </a>
      <div class="tgme_widget_message_text">Новина громади з посиланням</div>
      <time datetime="2026-09-14T10:00:00+00:00"></time>
    </div>
    """
    parser = StrictTelegramParser("community")
    parser.feed(html)
    parser.close()
    assert len(parser.entries) == 1
    urls = _urls(parser.entries[0])
    assert urls == ["https://cdn.example/preview.jpg"]
    assert "avatar.jpg" not in " ".join(urls)


def test_direct_media_wins_and_preview_is_not_added_as_second_image() -> None:
    html = """
    <div class="tgme_widget_message" data-post="community/201">
      <a class="tgme_widget_message_photo_wrap js-message_photo" style="background-image:url('https://cdn.example/direct.jpg')"></a>
      <a class="tgme_widget_message_link_preview" href="https://example.gov.ua/news/201">
        <i class="link_preview_image" style="background-image:url('https://cdn.example/preview.jpg')"></i>
      </a>
      <div class="tgme_widget_message_text">Новина громади з прямим фото</div>
      <time datetime="2026-09-14T10:01:00+00:00"></time>
    </div>
    """
    parser = StrictTelegramParser("community")
    parser.feed(html)
    parser.close()
    urls = _urls(parser.entries[0])
    assert urls == ["https://cdn.example/direct.jpg"]


def test_semantic_media_class_drift_is_accepted_inside_exact_widget() -> None:
    html = """
    <div class="tgme_widget_message" data-post="community/202">
      <div class="tgme_widget_message_link_preview">
        <a class="tgme_widget_message_media gallery_item" style="background-image:url('https://cdn.example/current-markup.jpg')"></a>
      </div>
      <div class="tgme_widget_message_text">Новий Telegram wrapper</div>
      <time datetime="2026-09-14T10:02:00+00:00"></time>
    </div>
    """
    parser = StrictTelegramParser("community")
    parser.feed(html)
    parser.close()
    assert _urls(parser.entries[0]) == ["https://cdn.example/current-markup.jpg"]
    article = strict_stitch_telegram("community", parser.entries)[0]
    layout = json.loads(article.article_layout_json)
    assert layout["telegram"]["media_filter_version"] == 5
    assert layout["telegram"]["media_filter"]["content_media"] == 1


def test_persistent_user_photo_ancestor_does_not_poison_real_post_photo() -> None:
    # Current t.me/s markup can leave the user-photo wrapper structurally open
    # around the bubble. Classification must use the candidate-local path, not
    # the union of every message ancestor.
    html = """
    <div class="tgme_widget_message" data-post="community/203">
      <a class="tgme_widget_message_user_photo bgcolor6" style="background-image:url('https://cdn.example/avatar.jpg')">
        <div class="tgme_widget_message_bubble">
          <a class="tgme_widget_message_photo_wrap js-message_photo" style="background-image:url('https://cdn.example/real.jpg')"></a>
          <div class="tgme_widget_message_text">Фото громади</div>
          <time datetime="2026-09-14T10:03:00+00:00"></time>
        </div>
      </a>
    </div>
    """
    parser = StrictTelegramParser("community")
    parser.feed(html)
    parser.close()
    assert len(parser.entries) == 1
    assert _urls(parser.entries[0]) == ["https://cdn.example/real.jpg"]
