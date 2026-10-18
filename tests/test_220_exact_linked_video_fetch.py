from types import SimpleNamespace

from telegram_autopilot.v2 import strict_ingest
from telegram_autopilot.models import Source


def test_linked_video_missing_from_listing_recovered_from_exact_post(monkeypatch):
    requested = []
    def fetch(url, **kwargs):
        requested.append(url)
        if "/s/community" in url:
            html = ('<div class="tgme_widget_message" data-post="community/100">'
                    '<div class="tgme_widget_message_text">'
                    'Дивіться відео https://t.me/community/101'
                    '</div></div>')
        else:
            html = ('<div class="tgme_widget_message" data-post="community/101">'
                    '<div class="tgme_widget_message_video_player">'
                    '<video src="https://example.org/clip.mp4"></video></div></div>')
        return SimpleNamespace(body=html.encode())
    monkeypatch.setattr(strict_ingest.collector, "_source_fetch", fetch)
    source = Source(
        id=1, channel_id=3, kind="telegram", name="Громада",
        url="https://t.me/community", enabled=True, initialized=True,
    )
    articles = strict_ingest.collect_telegram_strict(source)
    assert len(articles) == 1
    assert "https://t.me/community/101?embed=1&mode=tme" in requested
    import json
    tg = json.loads(articles[0].article_layout_json)["telegram"]
    assert tg["message_ids"] == ["100", "101"]


def test_mismatched_embed_cannot_recover_linked_video(monkeypatch):
    def fetch(url, **kwargs):
        if "/s/community" in url:
            html = ('<div class="tgme_widget_message" data-post="community/100">'
                    '<div class="tgme_widget_message_text">'
                    'Дивіться відео https://t.me/community/101'
                    '</div></div>')
        else:
            html = ('<div class="tgme_widget_message" data-post="community/999">'
                    '<div class="tgme_widget_message_video_player">'
                    '<video src="https://example.org/unrelated.mp4"></video></div></div>')
        return SimpleNamespace(body=html.encode())
    monkeypatch.setattr(strict_ingest.collector, "_source_fetch", fetch)
    source = Source(
        id=1, channel_id=3, kind="telegram", name="Громада",
        url="https://t.me/community", enabled=True, initialized=True,
    )
    articles = strict_ingest.collect_telegram_strict(source)
    import json
    tg = json.loads(articles[0].article_layout_json)["telegram"]
    assert tg["message_ids"] == ["100"]
