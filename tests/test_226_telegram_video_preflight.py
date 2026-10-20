"""v2.2.6: exact Telegram video integrity, including the bowling-club regression."""
from types import SimpleNamespace

from telegram_autopilot.v2 import telegram_post_preflight as preflight


def _fetch(html):
    called = []
    def stub(url, **kwargs):
        called.append(url)
        return SimpleNamespace(body=html.encode("utf-8"))
    return stub, called


def test_bowling_club_original_video_recovered_not_text_only(monkeypatch):
    html = ('<div class="tgme_widget_message" data-post="zaborzp/154789">'
            '<div class="tgme_widget_message_text">Колишній боулінг-клуб у Запоріжжі зараз перетворився на смітник.</div>'
            '<a class="tgme_widget_message_video_player"><video src="https://example.org/bowling.mp4"></video></a>'
            '</div>')
    stub, called = _fetch(html)
    monkeypatch.setattr(preflight.collector, "_source_fetch", stub)
    result = preflight.check_exact_telegram_video("https://t.me/zaborzp/154789")
    assert result.outcome == "video_recovered"
    assert len(result.video_media) == 1
    assert result.video_media[0].startswith("video|")
    assert called == ["https://t.me/zaborzp/154789?embed=1&mode=tme"]


def test_source_video_placeholder_never_degrades_to_text(monkeypatch):
    html = ('<div class="tgme_widget_message" data-post="zaborzp/154789">'
            '<div class="tgme_widget_message_text">Оригінальна новина з відео</div>'
            '<a class="tgme_widget_message_video_player">Завантажується...</a>'
            '</div>')
    stub, _ = _fetch(html)
    monkeypatch.setattr(preflight.collector, "_source_fetch", stub)
    result = preflight.check_exact_telegram_video("https://t.me/zaborzp/154789")
    assert result.outcome == "video_pending"
    assert result.video_signal == "html_video_class"


def test_unrelated_post_video_is_not_borrowed(monkeypatch):
    html = ('<div class="tgme_widget_message" data-post="zaborzp/154789">'
            '<div class="tgme_widget_message_text">Лише текст</div></div>'
            '<div class="tgme_widget_message" data-post="zaborzp/154790">'
            '<video src="https://example.org/other.mp4"></video></div>')
    stub, _ = _fetch(html)
    monkeypatch.setattr(preflight.collector, "_source_fetch", stub)
    assert preflight.check_exact_telegram_video("https://t.me/zaborzp/154789").outcome == "text_only"


def test_exact_embed_different_post_is_uncertain_not_safe(monkeypatch):
    stub, _ = _fetch('<div class="tgme_widget_message" data-post="zaborzp/154790">Окреме повідомлення</div>')
    monkeypatch.setattr(preflight.collector, "_source_fetch", stub)
    assert preflight.check_exact_telegram_video("https://t.me/zaborzp/154789").outcome == "uncertain"


def test_unavailable_source_is_retryable_not_assumed_text_only(monkeypatch):
    def broken(url, **kwargs):
        raise TimeoutError("simulated network failure")
    monkeypatch.setattr(preflight.collector, "_source_fetch", broken)
    result = preflight.check_exact_telegram_video("https://t.me/zaborzp/154789")
    assert result.outcome == "uncertain"
    assert "TimeoutError" in result.reason


def test_real_text_only_post_remains_publishable(monkeypatch):
    html = ('<div class="tgme_widget_message" data-post="zaborzp/154789">'
            '<div class="tgme_widget_message_text">Завтра відкриють ЦНАП.</div>'
            '</div>')
    stub, _ = _fetch(html)
    monkeypatch.setattr(preflight.collector, "_source_fetch", stub)
    assert preflight.check_exact_telegram_video("https://t.me/zaborzp/154789").outcome == "text_only"
