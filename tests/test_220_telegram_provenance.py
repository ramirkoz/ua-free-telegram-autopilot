import json
from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.strict_ingest import strict_stitch_telegram


def test_exact_widget_provenance_remains_bound_to_its_message():
    entries = [
        TelegramEntry(post="community/100", text="У громаді відбулося свято.",
                      published="2026-10-17T08:00:00+00:00"),
        TelegramEntry(post="community/101", text="", media=["image|https://example.org/photo.jpg"],
                      published="2026-10-17T08:01:00+00:00"),
    ]
    out = strict_stitch_telegram("community", entries)
    assert len(out) == 1
    meta = json.loads(out[0].article_layout_json)["telegram"]
    assert meta["source_boundary_provenance"] == "exact_telegram_widget"
    assert meta["source_provenance_complete"] is True
    assert [x["message_id"] for x in meta["source_message_records_v1"]] == ["100"]
    assert meta["source_message_records_v1"][0]["media_count"] == 0
    # Adjacent unrelated media cannot be falsely claimed as part of 100.
    assert "101" not in meta["message_ids"]


def test_source_widget_with_media_retains_same_post_provenance():
    entries = [TelegramEntry(post="community/200", text="Дивіться відео зустрічі.",
                             media=["video|https://example.org/a.mp4"],
                             published="2026-10-17T11:00:00+00:00")]
    out = strict_stitch_telegram("community", entries)
    assert len(out) == 1
    meta = json.loads(out[0].article_layout_json)["telegram"]
    assert meta["source_message_records_v1"][0]["media_count"] == 1
    assert meta["source_message_records_v1"][0]["post"] == "community/200"
