from types import SimpleNamespace
from telegram_autopilot.v2 import telegram_post_preflight as preflight

def inspect(monkeypatch, attachments):
    html = '<div class="tgme_widget_message" data-post="mih_gromada/4645"><div class="tgme_widget_message_text">Новини громади</div>' + attachments + '</div>'
    monkeypatch.setattr(preflight.collector, "_source_fetch", lambda *a, **kw: SimpleNamespace(body=html.encode()))
    return preflight.check_exact_telegram_media("https://t.me/mih_gromada/4645")

def photo(name):
    return '<a class="tgme_widget_message_photo_wrap" style="background-image:url(https://example.org/' + name + '.jpg)"></a>'

def test_collage(monkeypatch):
    check = inspect(monkeypatch, photo("irc"))
    assert check.outcome == "confirmed" and check.expected_photos == 1 and len(check.media) == 1

def test_two_images(monkeypatch):
    check = inspect(monkeypatch, photo("one") + photo("two"))
    assert check.outcome == "confirmed" and check.expected_photos == 2 and len(check.media) == 2

def test_partial_album(monkeypatch):
    check = inspect(monkeypatch, photo("one") + '<a class="tgme_widget_message_photo_wrap"></a>')
    assert check.outcome == "photo_pending" and check.expected_photos == 2

def test_missing_photo(monkeypatch):
    check = inspect(monkeypatch, '<a class="tgme_widget_message_photo_wrap"></a>')
    assert check.outcome == "photo_pending"

def test_text_only(monkeypatch):
    check = inspect(monkeypatch, "")
    assert check.outcome == "text_only" and not check.media
