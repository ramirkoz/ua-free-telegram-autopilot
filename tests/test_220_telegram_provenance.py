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
    assert meta["source_evidence_v1"][0]["quote"] == "У громаді відбулося свято."
    assert meta["source_evidence_v1"][0]["source_id"] == "community/100"
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


def test_explicit_reply_edge_recovers_separate_media_post():
    # Opposite-direction replies both prove linkage; simple adjacency does not.
    entries = [
        TelegramEntry(post="community/300", text="Відео зустрічі громади.",
                      published="2026-10-17T08:00:00+00:00"),
        TelegramEntry(post="community/301", text="", media=["video|https://example.org/v.mp4"],
                      published="2026-10-17T08:01:00+00:00",
                      reply_to_post="community/300"),
        TelegramEntry(post="community/302", text="", media=["image|https://example.org/unrelated.jpg"],
                      published="2026-10-17T08:01:02+00:00"),
    ]
    out = strict_stitch_telegram("community", entries)
    assert len(out) == 1
    meta = json.loads(out[0].article_layout_json)["telegram"]
    assert meta["message_ids"] == ["300", "301"]
    assert [x["message_id"] for x in meta["source_message_records_v1"]] == ["300", "301"]
    assert meta["source_provenance_complete"] is True
    assert "302" not in meta["message_ids"]


def test_parser_retains_reply_link_only_inside_telegram_reply_markup():
    from telegram_autopilot.v2.strict_ingest import StrictTelegramParser
    page = """
    <div class="tgme_widget_message" data-post="community/401">
      <a class="tgme_widget_message_reply" href="https://t.me/community/400">Reply</a>
      <div class="tgme_widget_message_text">Відео громади</div>
    </div>
    """
    parser = StrictTelegramParser("community")
    parser.feed(page)
    parser.close()
    assert parser.entries[0].reply_to_post == "community/400"


def test_ambiguous_media_claims_not_attached_to_two_news_stories():
    entries = [
        TelegramEntry(post="community/500", text="Подія одна.", published=None,
                      reply_to_post="community/502"),
        TelegramEntry(post="community/501", text="Подія друга.", published=None,
                      reply_to_post="community/502"),
        TelegramEntry(post="community/502", text="", published=None,
                      media=["video|https://example.org/unresolved.mp4"]),
    ]
    out = strict_stitch_telegram("community", entries)
    assert len(out) == 2
    for item in out:
        metadata = json.loads(item.article_layout_json)["telegram"]
        assert metadata["media_count"] == 0
        assert "502" not in metadata["message_ids"]
