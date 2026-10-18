import json
from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.strict_ingest import strict_stitch_telegram


def test_explicit_source_video_link_can_bind_exact_video_post():
    entries = [
        TelegramEntry(post="community/1000",
                      text="Дивіться друге відео https://t.me/community/1001",
                      published=None),
        TelegramEntry(post="community/1001", text="", published=None,
                      media=["video|https://example.org/original.mp4"]),
        TelegramEntry(post="community/1002", text="", published=None,
                      media=["video|https://example.org/unrelated.mp4"]),
    ]
    result = strict_stitch_telegram("community", entries)
    assert len(result) == 1
    tg = json.loads(result[0].article_layout_json)["telegram"]
    assert tg["message_ids"] == ["1000", "1001"]


def test_external_channel_and_image_only_link_are_not_video_ownership():
    entries = [
        TelegramEntry(post="community/2000",
                      text="Дивіться відео https://t.me/other_channel/2001 і https://t.me/community/2002",
                      published=None),
        TelegramEntry(post="community/2002", text="", published=None,
                      media=["https://example.org/still.jpg"]),
        TelegramEntry(post="community/2001", text="", published=None,
                      media=["video|https://example.org/unlinked.mp4"]),
    ]
    result = strict_stitch_telegram("community", entries)
    tg = json.loads(result[0].article_layout_json)["telegram"]
    assert tg["message_ids"] == ["2000"]


def test_explicit_link_claims_with_two_owners_remain_unbound():
    entries = [
        TelegramEntry(post="community/3000",
                      text="Перше відео https://t.me/community/3002", published=None),
        TelegramEntry(post="community/3001",
                      text="Друге відео https://t.me/community/3002", published=None),
        TelegramEntry(post="community/3002", text="", published=None,
                      media=["video|https://example.org/video.mp4"]),
    ]
    result = strict_stitch_telegram("community", entries)
    assert len(result) == 2
    assert all(json.loads(item.article_layout_json)["telegram"]["media_count"] == 0 for item in result)
