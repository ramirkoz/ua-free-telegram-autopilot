from types import SimpleNamespace

from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2 import strict_ingest


def test_exact_video_placeholder_retried_without_poster(monkeypatch):
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(body=(
            '<div class="tgme_widget_message" data-post="community/900">'
            '<div class="tgme_widget_message_video_player">'
            '<video src="https://example.org/clip.mp4"></video></div></div>'
        ).encode())
    monkeypatch.setattr(strict_ingest.collector, "_source_fetch", fetch)
    entry = TelegramEntry(post="community/900", text="", published=None, video_attachment_seen=True)
    found = strict_ingest._hydrate_exact_video_post("community", entry)
    assert calls == ["https://t.me/community/900?embed=1&mode=tme"]
    assert found.video_recovery == "exact_post_video"
    assert any(str(m).startswith("video|") for m in found.media)


def test_mismatched_single_embed_post_cannot_supply_video(monkeypatch):
    def fetch(url, **kwargs):
        return SimpleNamespace(body=(
            '<div class="tgme_widget_message" data-post="community/901">'
            '<div class="tgme_widget_message_video_player">'
            '<video src="https://example.org/unrelated.mp4"></video></div></div>'
        ).encode())
    monkeypatch.setattr(strict_ingest.collector, "_source_fetch", fetch)
    entry = TelegramEntry(post="community/900", text="", published=None, video_attachment_seen=True)
    found = strict_ingest._hydrate_exact_video_post("community", entry)
    assert found.post == "community/900"
    assert not found.media
    assert found.video_recovery == "no_video"


def test_exact_hydration_preserves_explicit_reply_and_group_metadata(monkeypatch):
    def fetch(url, **kwargs):
        return SimpleNamespace(body=(
            '<div class="tgme_widget_message" data-post="community/910">'
            '<div class="tgme_widget_message_video_player">'
            '<video src="https://example.org/video.mp4"></video></div></div>'
        ).encode())
    monkeypatch.setattr(strict_ingest.collector, "_source_fetch", fetch)
    entry = TelegramEntry(
        post="community/910", text="", published=None,
        video_attachment_seen=True, reply_to_post="community/909", grouped_id="album-1",
    )
    found = strict_ingest._hydrate_exact_video_post("community", entry)
    assert found.reply_to_post == "community/909"
    assert found.grouped_id == "album-1"
