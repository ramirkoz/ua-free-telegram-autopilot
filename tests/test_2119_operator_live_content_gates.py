from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject


def _channel():
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(monitoring_source_policy="connected_original"),
    )


def _article(text):
    return SimpleNamespace(
        raw_text=text, title=text, source_name="ЗаБор Запоріжжя",
        source_url="https://t.me/zaborzp/154305",
    )


def test_live_airstrike_destination_is_not_a_news_report():
    assert hard_editorial_reject(_channel(), _article("🚧 КАБи на Кушугум/Балабине"))


def test_generated_witness_is_not_supported_by_source():
    article = _article("У Запоріжжі відкрили новий центр допомоги родинам. Центр надаватиме консультації.")
    assert hard_editorial_reject(
        _channel(), article,
        "Місцеві жителі повідомляють про відкриття нового центру допомоги."
    ) == "MONITORING_UNGROUNDED_WITNESS"


def test_official_report_on_confirmed_damage_stays_eligible():
    article = _article("У Запоріжжі внаслідок ворожої атаки пошкоджено будинки. ОВА повідомила про поранених.")
    assert not hard_editorial_reject(_channel(), article)
