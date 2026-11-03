"""Regression evidence from installed Autopilot 2.3.5 operator SQLite (2026-11-03).

These are source-only exclusion checks, never new publication permissions.
"""
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion


def monitoring():
    return SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(rejection_rules="[LIVE_NOW_RC96]"),
    )


def article(text, title=""):
    return {"title": title, "raw_text": text}


def test_operator_89125_nonlocal_party_opinion_cannot_become_regional_news():
    src = ("Демократична партія дуже, дуже корумпована. "
           "Демократична партія висунула найекстремальніших кандидатів "
           "в американській історії.")
    assert "MONITORING_NONLOCAL_PARTISAN_OPINION" in civic_relevance_exclusion(
        monitoring(), article(src)
    )


def test_operator_89142_nonlocal_unverified_accusation_is_not_local_news():
    src = ("По Борщагівці ніхто поки не розуміє, що сталося. "
           "Чим далі, тим більше це схоже на ретельно сплановану підставу.")
    assert "MONITORING_UNVERIFIED_NONLOCAL_SPECULATION" in civic_relevance_exclusion(
        monitoring(), article(src)
    )


def test_operator_89172_source_sound_cannot_turn_into_aircraft_or_rocket_claim():
    src = "Ох ти! Яке жорстке сафарі по реактиву. Дуже чутно у Олександрівському."
    assert "Непідтверджене повідомлення" in live_now_exclusion(
        monitoring(), article(src)
    )


def test_specific_regional_public_services_are_not_blanket_blocked():
    src = ("У Запоріжжі погодили 199 заяв на компенсацію за житло після обстрілів. "
           "Загальна сума виплат становить майже 17,9 мільйона гривень.")
    assert civic_relevance_exclusion(monitoring(), article(src)) == ""


def test_documented_local_disaster_aftermath_is_not_sound_only():
    src = ("Внаслідок нічної атаки у Запоріжжі пошкоджено 7 будинків. "
           "Офіційно підтвердили наслідки обстрілу.")
    assert live_now_exclusion(monitoring(), article(src)) == ""


def test_utility_schedule_remains_eligible_for_editorial_fact_check():
    src = ("У Запоріжжі оприлюднили графік відключень світла. "
           "Для черги 1.1 заплановано відключення з 09:00 до 13:00.")
    assert live_now_exclusion(monitoring(), article(src)) == ""
