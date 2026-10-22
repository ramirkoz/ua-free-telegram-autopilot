"""Autopilot 2.2.17: real operator 2026-10-22 article #72838/#72839.

Reject nationwide daily military-loss totals even when a Zaporizhzhia-based
source forwards them; retain real local events. Recognize source-owned days
glued by Telegram extraction, without dropping invented-number protection.
"""
from __future__ import annotations

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import (
    _number_tokens, validate_writer_output, hard_editorial_reject,
    deterministic_monitoring_exclusion, prepublish_quality_issues,
)
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion


def monitor(*, opt_in=True, mode=ChannelMode.MONITORING):
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-100123",
        mode=mode, policy=ChannelPolicy(
            channel_id=3,
            rejection_rules="[LIVE_NOW_RC96]" if opt_in else "",
        ),
    )


def article(raw, *, source="https://t.me/zaborzp/155080"):
    return {
        "id": 72838, "channel_id": 3, "source_id": 191,
        "title": raw[:250], "raw_text": raw,
        "source_name": "ЗаБор Запоріжжя", "source_url": source,
        "canonical_source_url": source,
    }


NATIONAL_ROLLUP = (
    "🚧☠🔥 Отакої! ⚡️Рекорд ліквідації росіян за добу: Генштаб "
    "зафіксував найбільші добові втрати армії рф від початку "
    "повномасштабної війниВтрати ворога за добу становлять 2250 осіб."
)
LOCAL_TRANSPORT = (
    "🚎 У Запоріжжі змінили рух громадського транспорту через "
    "перекриття греблі ДніпроГЕС для громадського транспорту22 жовтня "
    "автобуси й тролейбуси не курсуватимуть через греблю. "
    "Тролейбус № 8 курсуватиме між площею Запорізькою та вокзалом."
)


def test_operator_72838_blocked_in_all_civic_gates_even_with_local_source_brand():
    ch=monitor()
    row=article(NATIONAL_ROLLUP)
    assert civic_relevance_exclusion(ch,row).startswith("MONITORING_OFF_TOPIC_DAILY_LOSSES")
    assert live_now_exclusion(ch,row).startswith("MONITORING_OFF_TOPIC_DAILY_LOSSES")
    assert deterministic_monitoring_exclusion(ch,row).startswith("MONITORING_OFF_TOPIC_DAILY_LOSSES")
    assert hard_editorial_reject(ch,row,"Генштаб повідомив про втрати російських військових").startswith(
        "MONITORING_OFF_TOPIC_DAILY_LOSSES"
    )
    assert any("MONITORING_OFF_TOPIC_DAILY_LOSSES" in reason for reason in
               prepublish_quality_issues(ch,row,"Генштаб повідомив про рекордні втрати армії рф."))
    # Does not depend on name/id of the publisher.
    row["source_name"]="Міська редакція"
    assert civic_relevance_exclusion(ch,row).startswith("MONITORING_OFF_TOPIC_DAILY_LOSSES")


@pytest.mark.parametrize("source",[
    "Генштаб повідомив: втрати російської армії за добу становлять 2250 військових.",
    "Росія втратила за добу 1500 військових: дані Генштабу.",
    "За добу ліквідовано 1700 окупантів по всій країні.",
])
def test_national_daily_rollups_blocked(source):
    assert civic_relevance_exclusion(monitor(),article(source)).startswith("MONITORING_OFF_TOPIC_DAILY_LOSSES")


@pytest.mark.parametrize("source",[
    LOCAL_TRANSPORT,
    "У Запоріжжі після обстрілу пошкоджені 12 будинків та поранені троє цивільних.",
    "У Запоріжжі відкривають прихисток для сімей та записують переселенців.",
    "На Запорізькому напрямку повідомили про втрати військ рф, у Запоріжжі "
    "рятувальники відновлюють будинки постраждалих мешканців.",
    "Генштаб повідомив про втрати росіян за добу. На Запоріжжі передали "
    "генератори сім'ям у Пологівській громаді.",
])
def test_real_local_and_civilian_outcomes_not_blocked(source):
    assert civic_relevance_exclusion(monitor(),article(source))==""


def test_opt_in_is_required():
    for ch in (monitor(opt_in=False), monitor(mode=ChannelMode.EDITORIAL)):
        assert civic_relevance_exclusion(ch,article(NATIONAL_ROLLUP))==""


def test_72839_glued_ukrainian_month_is_real_supported_day():
    src = article(LOCAL_TRANSPORT,source="https://t.me/bezbaidy/42419")
    assert "22" in _number_tokens(src["raw_text"])
    assert "22" in _number_tokens("22 жовтня у Запоріжжі змінять рух транспорту.")
    assert "23" not in _number_tokens(src["raw_text"])
    assert "22" not in _number_tokens("GPT22 підтримує режими. iPhone22 випущено.")
    good = (
        "У Запоріжжі 22 жовтня змінюють маршрути громадського транспорту "
        "через перекриття греблі ДніпроГЕС. Автобуси й тролейбуси "
        "перенаправляють на альтернативні маршрути."
    )
    assert validate_writer_output(src,good,min_chars=60,max_chars=750)
    bad = good.replace("22 жовтня","23 жовтня")
    with pytest.raises(ValueError,match="AI додав число|Fact"):
        validate_writer_output(src,bad,min_chars=60,max_chars=750)


@pytest.mark.parametrize("month",["жовтня","березня","листопада","січня","травня"])
def test_source_parser_glued_dates_and_product_names(month):
    assert "22" in _number_tokens(f"маршруту22 {month} діє розклад.")
    assert "22" not in _number_tokens("iPhone22 це позначення моделі, не календарна дата.")
