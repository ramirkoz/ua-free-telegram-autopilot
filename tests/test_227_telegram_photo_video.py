from types import SimpleNamespace
from telegram_autopilot.v2 import telegram_post_preflight as p

def _inspect(monkeypatch, attachment):
    html = '<div class="tgme_widget_message" data-post="mih_gromada/4645"><div class="tgme_widget_message_text">Новина</div>' + attachment + '</div>'
    monkeypatch.setattr(p.collector, "_source_fetch", lambda *a, **k: SimpleNamespace(body=html.encode()))
    return p.check_exact_telegram_media("https://t.me/mih_gromada/4645")

def test_photo_cannot_replace_video(monkeypatch):
    markup = '<a class="tgme_widget_message_photo_wrap" style="background-image:url(https://example.org/pic.jpg)"></a><a class="tgme_widget_message_video_player">loading</a>'
    result = _inspect(monkeypatch, markup)
    assert result.outcome == "video_pending"
    assert p.source_media_shortfall(result, result.media) == "TELEGRAM_VIDEO_PENDING"

def test_photo_and_video_both_required(monkeypatch):
    markup = '<a class="tgme_widget_message_photo_wrap" style="background-image:url(https://example.org/pic.jpg)"></a><video src="https://example.org/clip.mp4"></video>'
    result = _inspect(monkeypatch, markup)
    assert result.outcome == "confirmed" and result.video_expected
    assert result.expected_photos == 1 and not p.source_media_shortfall(result, result.media)
