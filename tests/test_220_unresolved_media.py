import json

from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.strict_ingest import strict_stitch_telegram
from telegram_autopilot.v2.unresolved_media import observe_nearby_unowned_media


def test_unlinked_nearby_video_is_recorded_but_not_stolen():
    entries = [
        TelegramEntry(post="community/800", text="Дивіться друге відео зі свята.",
                      published="2026-10-18T10:00:00+00:00"),
        TelegramEntry(post="community/801", text="", published="2026-10-18T10:01:00+00:00",
                      media=["video|https://example.org/clip.mp4"]),
    ]
    out = strict_stitch_telegram("community", entries)
    assert len(out) == 1
    layout = json.loads(out[0].article_layout_json)["telegram"]
    assert layout["message_ids"] == ["800"]
    assert layout["media_count"] == 0
    assert layout["media_ownership_unresolved"] is True
    assert layout["unresolved_nearby_media_v1"][0]["post"] == "community/801"
    assert layout["unresolved_nearby_media_v1"][0]["video_seen"] is True


def test_explicit_reply_video_not_marked_unresolved():
    entries = [
        TelegramEntry(post="community/820", text="Дивіться відео.",
                      published="2026-10-18T10:00:00+00:00"),
        TelegramEntry(post="community/821", text="", published="2026-10-18T10:01:00+00:00",
                      reply_to_post="community/820",
                      media=["video|https://example.org/clip.mp4"]),
    ]
    out = strict_stitch_telegram("community", entries)
    layout = json.loads(out[0].article_layout_json)["telegram"]
    assert layout["message_ids"] == ["820", "821"]
    assert not layout.get("media_ownership_unresolved", False)


def test_unresolved_neighbor_requires_source_and_time_boundaries():
    origin = TelegramEntry(post="a/1", text="Оголошення", published="2026-10-18T10:00:00+00:00")
    different_channel = TelegramEntry(post="b/2", text="", published="2026-10-18T10:01:00+00:00",
                                      media=["video|https://example.org/one.mp4"])
    old = TelegramEntry(post="a/3", text="", published="2026-10-18T11:00:00+00:00",
                        media=["video|https://example.org/two.mp4"])
    assert not observe_nearby_unowned_media(origin, (different_channel, old))
