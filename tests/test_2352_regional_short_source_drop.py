"""Owner 2.3.67: length is not a regional veto; facts remain mandatory."""
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.monitoring_short_material_2352 import (
    MIN_REGIONAL_NEWS_CHARS,
    monitoring_short_material_reason_2352,
)


def regional(min_chars=500):
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(
            target_min_chars=min_chars,
            target_max_chars=1000,
            monitoring_source_policy="connected_original",
            rejection_rules="[LIVE_NOW_RC96]",
        ),
    )


def article(text):
    return SimpleNamespace(
        title=text, raw_text=text, source_name="ЗаБор Запоріжжя",
        source_url="https://t.me/zaborzp/160771",
        article_layout_json="{}",
    )


def test_short_traffic_source_not_dropped_for_length():
    source = (
        "У Запоріжжі на вулиці Марії Примаченко зранку лежало тіло "
        "людини. На місці перебували дві поліцейські машини, "
        "причина події невідома. Рух бульваром Марії Примаченко "
        "відновлено, повідомляє поліція."
    )
    item = article(source)
    assert monitoring_short_material_reason_2352(regional(), item) == ""
    assert hard_editorial_reject(regional(), item) == ""
    assert hard_editorial_reject(regional(), item, "Говорять про відновлення руху.") != "MONITORING_SHORT_SOURCE_DROP_2352"


def test_short_final_not_rejected_for_length_alone():
    original = (
        "У Запорізькій області місцева адміністрація оприлюднила "
        "нові дані про порядок роботи закладу для жителів громади. "
        "Опубліковані адреса, дата, час приймання, перелік "
        "послуг, відповідальні особи та порядок звернення. "
    ) * 4
    text = "У Запоріжжі відновили рух бульваром Марії Примаченко. Зранку на узбіччі лежало тіло людини."
    assert len(original) > 500 and len(text) < 500
    assert monitoring_short_material_reason_2352(regional(), article(original), text) == ""


def test_short_fact_with_link_does_not_need_padding():
    short = "У Запоріжжі відновили рух. " + ("https://t.me/zaborzp/160771 " * 40)
    assert len(short) > 500
    assert monitoring_short_material_reason_2352(regional(), article(short)) == ""


def test_qualified_long_story_and_faithful_500_char_final_remain_possible():
    text = (
        "Запорізька міська рада оприлюднила підсумки завершених "
        "робіт у громаді та повідомила, які об'єкти вже "
        "працюють. У повідомленні наведено точні адреси, "
        "дати завершення та відповідальні комунальні служби. "
    ) * 4
    assert len(text) > MIN_REGIONAL_NEWS_CHARS
    assert monitoring_short_material_reason_2352(regional(), article(text), text) == ""
    assert monitoring_short_material_reason_2352(regional(600), article(text), text[:525]) == ""


def test_only_regional_news_channel_no_cross_channel_regression():
    short = article("Новий гаджет випустили у продаж.")
    for channel_id, mode in ((1, ChannelMode.EDITORIAL), (2, ChannelMode.EDITORIAL)):
        other = ChannelConfig(
            id=channel_id, name="Other", telegram_chat_id="@test",
            mode=mode, policy=ChannelPolicy(target_min_chars=500),
        )
        assert monitoring_short_material_reason_2352(other, short) == ""


def test_configured_length_is_nonbinding_for_regional_dispatches():
    # The operator's current production min=500 is authoritative; generic
    # historical test profiles targeting 120/300 are not silently rewritten.
    assert monitoring_short_material_reason_2352(
        regional(120), article("Відновили рух бульваром.")
    ) == ""
    assert monitoring_short_material_reason_2352(
        regional(500), article("Відновили рух бульваром.")
    ) == ""
