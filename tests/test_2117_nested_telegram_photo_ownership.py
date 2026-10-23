"""Regression: municipal direct photos wrapped by Telegram channel header chrome.

LIVE Data(7).zip / article #56221 / osypenko_stg/4739:
raw_candidates=8, discarded_non_content=8, content_media=0; the exact
public HTML is not included in the backup. Test the observed failure class
without misrepresenting this fixture as a captured copy of the source DOM.
"""
from telegram_autopilot.v2.strict_ingest import StrictTelegramParser
from telegram_autopilot.v2.telegram_ingest_policy import stitch_adjacent_telegram_media


def _parse(html):
    parser = StrictTelegramParser("osypenko_stg")
    parser.feed(html)
    parser.close()
    return parser.entries


def test_nested_message_photo_survives_outer_user_photo_wrapper():
    html = """
    <div class="tgme_widget_message" data-post="osypenko_stg/4739">
      <div class="tgme_widget_message_user_photo">
        <img src="https://example.test/avatar.jpg"/>
        <div class="tgme_widget_message_photo_wrap">
          <a class="js-message_photo" style="background-image:url('https://example.test/meeting.jpg')"></a>
        </div>
        <div class="tgme_widget_message_text">Зустріч Осипенківської громади</div>
      </div>
      <time datetime="2026-10-15T18:05:52+03:00"></time>
    </div>"""
    entries = _parse(html)
    assert len(entries) == 1
    assert len(entries[0].media) == 1
    assert "meeting.jpg" in entries[0].media[0]
    assert not any("avatar.jpg" in item for item in entries[0].media)


def test_nested_photo_wrapper_recognized_when_candidate_has_plain_classes():
    html = """
    <div class="tgme_widget_message" data-post="osypenko_stg/4740">
      <div class="tgme_widget_message_photo_wrap">
        <div class="photo-inner"><span class="photo-inner-more">
          <i style="background-image:url('https://example.test/meeting2.jpg')"></i>
        </span></div>
      </div>
      <time datetime="2026-10-15T18:06:00+03:00"></time>
    </div>"""
    entries = _parse(html)
    assert len(entries) == 1
    assert len(entries[0].media) == 1
    assert "meeting2.jpg" in entries[0].media[0]


def test_real_avatar_without_direct_media_marker_never_published():
    html = """
    <div class="tgme_widget_message" data-post="osypenko_stg/4741">
      <a class="tgme_widget_message_user_photo">
        <img src="https://example.test/avatar.jpg"/>
      </a>
      <div class="tgme_widget_message_text">Новина без фото</div>
      <time datetime="2026-10-15T18:06:10+03:00"></time>
    </div>"""
    entries = _parse(html)
    assert len(entries) == 1
    assert entries[0].media == []


def test_media_in_next_unlinked_post_does_not_stitch():
    html = """
    <div class="tgme_widget_message" data-post="osypenko_stg/500">
      <div class="tgme_widget_message_text">Відбулася зустріч громади</div>
      <time datetime="2026-10-15T18:05:00+03:00"></time>
    </div>
    <div class="tgme_widget_message" data-post="osypenko_stg/501">
      <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://example.test/meeting.jpg')"></a>
      <time datetime="2026-10-15T18:05:20+03:00"></time>
    </div>"""
    articles = stitch_adjacent_telegram_media("osypenko_stg", _parse(html))
    assert len(articles) == 1
    assert len(articles[0].media_urls) == 0
