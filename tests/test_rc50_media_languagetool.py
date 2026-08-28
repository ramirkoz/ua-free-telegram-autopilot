from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import telegram_autopilot.language_tool_local as lt
from telegram_autopilot.article_extractor import editorial_media_candidate
from telegram_autopilot.media_pipeline import PreparedMedia, _hard_reject
from telegram_autopilot.service import _marketing_media_context


def test_languagetool_operator_status_uses_realistic_health_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(lt, "_probe_server", lambda *, timeout: calls.append(timeout) or False)
    monkeypatch.setattr(lt, "_find_server_jar", lambda: None)
    monkeypatch.setattr(lt, "_read_stats", lambda: {})
    lt.languagetool_status()
    assert calls and calls[0] >= 3.0


def test_marketing_context_does_not_treat_campaign_vocabulary_as_junk():
    item = PreparedMedia(1, "image", "https://example.com/advertisement/promo-campaign.jpg", context="marketing promotion creative")
    assert _hard_reject(item)
    assert not _hard_reject(item, marketing_context=True)


def test_marketing_context_still_rejects_sponsored_banner_noise():
    item = PreparedMedia(1, "image", "https://example.com/sponsored/banner.jpg", context="affiliate sponsored banner")
    assert _hard_reject(item, marketing_context=True)


def test_default_context_still_rejects_advertising_commercial_metadata():
    item = PreparedMedia(1, "image", "https://example.com/campaign.jpg", context="advertising commercial creative")
    assert _hard_reject(item)
    assert not _hard_reject(item, marketing_context=True)


def test_extractor_defers_topical_promo_words_to_channel_policy():
    url = editorial_media_candidate(
        "https://example.com/story", "/advertising/promo-campaign.jpg",
        context="marketing advertisement promotion campaign creative", width=1200, height=800,
    )
    assert url.endswith("/advertising/promo-campaign.jpg")


def test_extractor_keeps_unambiguous_sponsored_noise_blocked():
    assert not editorial_media_candidate(
        "https://example.com/story", "/sponsored/banner.jpg",
        context="sponsored affiliate banner", width=1200, height=800,
    )


def test_prodano_is_detected_as_marketing_media_context():
    channel = SimpleNamespace(name="ПРОДАНО!", editorial_profile="Реклама, бренди і все, що продає увагу")
    assert _marketing_media_context(channel)


def test_service_has_no_text_only_telegram_fallback():
    source = (Path(__file__).resolve().parents[1] / "telegram_autopilot" / "service.py").read_text(encoding="utf-8")
    assert "send_text(" not in source
    assert "публікація без медіа заборонена для всіх каналів" in source
