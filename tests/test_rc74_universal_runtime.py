from __future__ import annotations

from types import SimpleNamespace

from telegram_autopilot import rc45_policy as rc45
from telegram_autopilot import rc74_universal_runtime as rc74


def _media(url: str, context: str = ""):
    return SimpleNamespace(url=url, context=context)


def test_channel_context_uses_explicit_direction_and_restores():
    before = rc45._CURRENT_DIRECTION.get()
    channel = SimpleNamespace(content_direction="ukru_to_en")
    with rc74.channel_context(channel) as direction:
        assert direction == "ukru_to_en"
        assert rc45._CURRENT_DIRECTION.get() == "ukru_to_en"
        assert rc74.source_labels() == ("Source", "Sources")
    assert rc45._CURRENT_DIRECTION.get() == before


def test_channel_context_does_not_use_channel_name():
    # EN->UK is part of the base direction registry even before the later UI
    # extensions are installed, so this unit test remains isolated.
    channel = SimpleNamespace(name="anything", editorial_profile="anything", content_direction="en_to_uk")
    with rc74.channel_context(channel):
        assert rc45._CURRENT_DIRECTION.get() == "en_to_uk"
        assert rc74.source_labels() == ("Джерело", "Джерела")


def test_media_hard_gate_is_channel_neutral():
    editorial = _media("https://example.com/campaign-advertisement-commercial-promo.jpg", "article body")
    assert rc74.universal_media_hard_reject(editorial, marketing_context=False) is False
    assert rc74.universal_media_hard_reject(editorial, marketing_context=True) is False

    tracker = _media("https://doubleclick.net/tracking/pixel.gif", "article body")
    assert rc74.universal_media_hard_reject(tracker, marketing_context=False) is True
    assert rc74.universal_media_hard_reject(tracker, marketing_context=True) is True


def test_source_link_entity_supports_both_output_languages():
    ua = "Текст\n\nДжерело"
    en = "Text\n\nSource"
    assert '"url":"https://example.com/a"' in rc74._source_link_entities_rc74(ua, "https://example.com/a")
    assert '"url":"https://example.com/b"' in rc74._source_link_entities_rc74(en, "https://example.com/b")


def test_rc74_contains_no_known_channel_routing_names():
    source = open(rc74.__file__, "r", encoding="utf-8").read().casefold()
    assert "продано" not in source
    assert "ctrl+ua" not in source
    assert "ctrlua" not in source


def test_legacy_channel_specific_layers_are_not_active_in_main():
    import telegram_autopilot.main as main

    source = open(main.__file__, "r", encoding="utf-8").read()
    assert "install_rc62_editorial_control()" not in source
    assert "install_rc63_training_mode()" not in source
    assert "install_rc64_live_tuning()" not in source
