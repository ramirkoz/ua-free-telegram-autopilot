"""Positive as well as negative video acceptance cases.

The suite exercises ingestion -> source-owned media -> editorial media decision,
rather than treating a green "reject" test as proof of working publication.
"""
import json
from types import SimpleNamespace

from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.strict_ingest import strict_stitch_telegram
from telegram_autopilot.v2.evidence_first import assess_monitoring_media


def _article_for_gate(collected):
    return SimpleNamespace(
        source_url=collected.url,
        raw_text=collected.raw_text,
        media_json=json.dumps(collected.media_urls),
        article_layout_json=collected.article_layout_json,
    )


def test_verified_reply_video_can_proceed_past_media_integrity_gate():
    source = [
        TelegramEntry(post="community/150", text="На святі громади показали виступи. Дивіться відео події.",
                      published="2026-10-18T10:00:00+00:00"),
        TelegramEntry(post="community/151", text="", published="2026-10-18T10:01:00+00:00",
                      reply_to_post="community/150", media=["video|https://example.org/recording.mp4"]),
    ]
    articles = strict_stitch_telegram("community", source)
    assert len(articles) == 1
    item = articles[0]
    assert item.media_urls == ["video|https://example.org/recording.mp4"]
    assert json.loads(item.article_layout_json)["telegram"]["message_ids"] == ["150", "151"]
    assert assess_monitoring_media(_article_for_gate(item), final_text="На святі громади показали виступи. Дивіться відео події.").allowed


def test_verified_grouped_video_can_proceed_past_media_integrity_gate():
    entries = [
        TelegramEntry(post="community/250", text="Дивіться відео із зустрічі громади.",
                      published=None, grouped_id="album-confirmed"),
        TelegramEntry(post="community/251", text="", published=None, grouped_id="album-confirmed",
                      media=["video|https://example.org/meeting.mp4"]),
    ]
    item = strict_stitch_telegram("community", entries)[0]
    assert assess_monitoring_media(_article_for_gate(item), final_text=item.raw_text).allowed


def test_missing_video_stays_blocked_and_unrelated_photo_never_satisfies_it():
    entries = [
        TelegramEntry(post="community/350", text="Дивіться відео зі свята.",
                      published="2026-10-18T10:00:00+00:00"),
        TelegramEntry(post="community/351", text="", published="2026-10-18T10:01:00+00:00",
                      media=["https://example.org/unrelated-photo.jpg"]),
    ]
    item = strict_stitch_telegram("community", entries)[0]
    assert item.media_urls == []
    decision = assess_monitoring_media(_article_for_gate(item), final_text=item.raw_text)
    assert decision.reasons == ("MONITORING_VIDEO_ATTACHMENT_UNBOUND",)
