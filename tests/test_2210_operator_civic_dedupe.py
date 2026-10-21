"""2.2.10 operator screenshot regressions: civic relevance and actual local event identity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.municipal_event_identity import municipal_same_event
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


def channel(opt_in: bool = True):
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1003",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96] Обов'язкове відхилення live-now." if opt_in else ""),
    )


def article(text: str):
    return {"title": text, "raw_text": text, "source_id": 191, "source_url": "https://example.org/a"}


@pytest.mark.parametrize("text,code", [
    ("Росіяни продовжують просування на Гуляйпільському напрямку поблизу села Криничне.", "MONITORING_TACTICAL_UPDATE"),
    ("Росіяни просунулися у Запорізькій області поблизу села. Наступ триває.", "MONITORING_TACTICAL_UPDATE"),
    ("Для ВПО Великобілозерської громади опублікували актуальні вакансії в Запоріжжі. Посилання у дописі.", "MONITORING_OFF_TOPIC"),
    ("Енергодар. За сьогодні там згоріло майно російських військових і є втрати серед них. Пишуть про жмурки.", "MONITORING_OFF_TOPIC"),
])
def test_unwanted_operator_examples_blocked_before_ai(text,code):
    assert code in civic_relevance_exclusion(channel(), article(text))
    assert code in live_now_exclusion(channel(), article(text))


@pytest.mark.parametrize("text", [
    "В Олександрівському районі Запоріжжя встановлюють модульне укриття.",
    "Внаслідок нічної атаки пошкоджено 12 житлових будинків і є постраждалі мешканці.",
    "Громадський парк оприлюднив карту екологічних маршрутів і програму екскурсій.",
    "Для ВПО відкрили центр зайнятості та навчання у Запоріжжі.",
])
def test_legitimate_civic_items_are_not_rejected_by_new_policy(text):
    assert not civic_relevance_exclusion(channel(), article(text))


def test_other_unopted_monitoring_channels_are_not_changed():
    assert not civic_relevance_exclusion(channel(False), article(
        "Росіяни продовжують просування на Гуляйпільському напрямку поблизу села."
    ))


def story(title: str, raw: str, source_id: int, at: str = "2026-10-20T20:00:00+03:00"):
    return {
        "title": title, "raw_text": raw, "source_id": source_id,
        "source_url": f"https://example.org/{source_id}",
        "source_published_at": at,
    }


FIRST = story(
    "На вулиці Лісогірній в Олександрівському районі Запоріжжя встановлюють модульне укриття",
    "Монтажні роботи вже тривають.", 190,
)
SECOND = story(
    "Біля запорізького парку «Дубовий Гай» встановлюють нове модульне укриття",
    "Роботи проводять за підтримки УВКБ ООН. Про це повідомила Олександрівська районна адміністрація.",
    191, "2026-10-20T22:00:00+03:00",
)


def test_shelter_same_district_and_phase_without_same_site_is_not_automatically_duplicate():
    # 2.2.10 used a district-only identity for the street/park reports;
    # the operator's original screenshots did not establish a shared exact site.
    # Fail open rather than silence another real shelter in the same district.
    assert not municipal_same_event(FIRST, SECOND)[0]


def test_shelter_same_exact_park_and_stage_across_sources_is_duplicate():
    first = story("У парку Дубовий Гай у Запоріжжі монтують модульне укриття",
                  "Почався монтаж біля парку Дубовий Гай.", 190)
    second = story("В Запоріжжі встановлюють нове модульне укриття",
                   "Роботи біля парку Дубовий Гай тривають.", 191)
    yes, why = municipal_same_event(first, second)
    assert yes, why
    assert "phase=installing" in why
    assert "park:" in why


def test_distinct_sites_are_not_merged():
    one=story("На вулиці Лісогірній в Олександрівському районі Запоріжжя встановлюють модульне укриття","Монтаж триває.",190)
    two=story("На вулиці Шкільній в Олександрівському районі Запоріжжя встановлюють модульне укриття","Монтаж триває.",191)
    assert not municipal_same_event(one,two)[0]


def test_different_districts_are_not_merged():
    other=story("У Шевченківському районі Запоріжжя встановлюють модульне укриття","Монтажні роботи тривають.",191)
    assert not municipal_same_event(FIRST,other)[0]


def test_material_stage_change_is_not_duplicate():
    opened=story("В Олександрівському районі Запоріжжя відкрили модульне укриття",
                 "Укриття поруч із парком Дубовий Гай вже відкрите для відвідувачів", 191)
    assert not municipal_same_event(FIRST,opened)[0]


def test_distant_repeat_does_not_suppress_new_event():
    later=dict(SECOND,source_published_at="2026-11-02T22:00:00+03:00")
    assert not municipal_same_event(FIRST,later)[0]


def test_generic_similar_topic_is_not_duplicate():
    bus=story("В Олександрівському районі Запоріжжя ремонтують автобусні зупинки",
              "Монтажні роботи вже тривають",191)
    assert not municipal_same_event(FIRST,bus)[0]


def test_same_source_does_not_trigger_cross_source_lane():
    again=dict(SECOND,source_id=FIRST["source_id"])
    assert not municipal_same_event(FIRST,again)[0]
