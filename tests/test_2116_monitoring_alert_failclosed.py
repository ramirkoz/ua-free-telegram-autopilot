"""Live 56082 regression: alert-level notice is not a community news story."""
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject, EditorialEngine
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion


def _channel():
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1001",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96] Не брати live-now сигнали"),
    )


def _article(text):
    return {"title": text, "raw_text": text, "source_name": "Оріхівська громада",
            "source_url": "https://t.me/ormr_gov_ua/22199"}


def test_red_level_live_56082_rejected_before_ai():
    text = "🔴 Рівень підвищено до червоного 📍 Запорізький район 📍 Запоріжжя. У Запорізькому районі та Запоріжжі рівень небезпеки підвищили до червоного. Будьте обережні."
    assert hard_editorial_reject(_channel(), _article(text)) == "MONITORING_LIVE_DANGER_LEVEL"


def test_other_danger_levels_and_decrease_rejected():
    for text in (
        "Рівень небезпеки підвищили до помаранчевого. Будьте обережні.",
        "У районі рівень загрози знижено до жовтого. Слідкуйте за сигналами.",
        "Рівень небезпеки тепер червоний. Прохання бути обережними.",
    ):
        assert hard_editorial_reject(_channel(), _article(text)) == "MONITORING_LIVE_DANGER_LEVEL"


def test_confirmed_results_and_concrete_actions_not_blindly_blocked():
    for text in (
        "Після атаки пошкоджено 12 будинків. Рівень небезпеки підвищили до червоного.",
        "Рівень небезпеки підвищили до червоного. Влада оголосила евакуацію двох вулиць.",
        "Сьогодні відкрили центр допомоги жителям Запоріжжя.",
    ):
        assert hard_editorial_reject(_channel(), _article(text)) != "MONITORING_LIVE_DANGER_LEVEL"


def test_text_album_not_touched_by_alert_policy():
    from telegram_autopilot.v2.telegram_ingest_policy import stitch_adjacent_telegram_media
    from telegram_autopilot.v2.ingest import TelegramEntry
    from telegram_autopilot.media import encode_media
    rows = [
        TelegramEntry(post="community/101", text="У громаді відкрили нову бібліотеку",
                      published="2026-10-15T12:00:00+00:00", media=[]),
        TelegramEntry(post="community/102", text="", published="2026-10-15T12:00:10+00:00",
                      media=[encode_media("image", "https://example.test/image.jpg")]),
    ]
    result = stitch_adjacent_telegram_media("community", rows)
    assert len(result) == 1
    assert len(result[0].media_urls) == 1
