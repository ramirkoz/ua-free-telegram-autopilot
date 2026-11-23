"""2.3.51 LIVE regressions: Telegram #5712, #5713, #5714, 23 Nov.

Fixture IDs and origin links document the incident, never act as rules.
"""
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.monitoring_source_context_2351 import (
    monitoring_source_context_reason_2351,
    monitoring_final_context_issue_2351,
)


def row(text, title=""):
    return {"raw_text": text, "title": title or text}


def channel():
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(
            monitoring_source_policy="connected_original",
            rejection_rules="[LIVE_NOW_RC96]",
        ),
    )


def test_111168_5714_other_channels_pinned_schedule_is_not_news():
    """The donor channel's navigation was falsely selected with fit=100."""
    text = (
        "💡⁉️Запоріжці, також нагадуємо, що у нас завжди закріплено "
        "актуальний графік відключень світла в шапці каналу. "
        "Слідкуємо за оновленнями обленерго, щоб якомога швидше "
        "повідомляти про зміни."
    )
    assert monitoring_source_context_reason_2351(row(text)) == (
        "MONITORING_DONOR_PINNED_SCHEDULE_NOT_NEWS_2351"
    )
    item = SimpleNamespace(
        title=text, raw_text=text, source_name="INFORM.ZP",
        source_url="https://t.me/informzp1/89510",
        article_layout_json="{}",
    )
    assert hard_editorial_reject(channel(), item) == (
        "MONITORING_DONOR_PINNED_SCHEDULE_NOT_NEWS_2351"
    )
    # A model/READY imported from before upgrade cannot bypass this source veto.
    assert hard_editorial_reject(
        channel(), item, "Графік доступний у шапці іншого каналу."
    ) == "MONITORING_DONOR_PINNED_SCHEDULE_NOT_NEWS_2351"


def test_genuine_schedule_remains_eligible_even_with_channel_reference():
    original = (
        "У Запоріжжі оновили графік відключень на 24 листопада. "
        "Група 1.1: 07:00–12:00, група 2.1: 16:30–20:30. "
        "Повна таблиця закріплена у шапці каналу."
    )
    assert not monitoring_source_context_reason_2351(row(original))


def test_111129_5712_orphan_three_deaths_floor_unknown_target_blocked():
    original = (
        "😢Фото наслідків атаки публікує Запорізька ОВА."
        "😭Три людини загинули, повідомили в ОВА. "
        "На третьому поверсі виникла пожежа. Її вже локалізували."
    )
    assert monitoring_source_context_reason_2351(row(original)) == (
        "MONITORING_ORPHAN_CASUALTY_FRAGMENT_2351"
    )
    item = SimpleNamespace(
        title=original, raw_text=original, source_name="INFORM.ZP",
        source_url="https://t.me/informzp1/89504",
        article_layout_json="{}",
    )
    assert hard_editorial_reject(channel(), item) == (
        "MONITORING_ORPHAN_CASUALTY_FRAGMENT_2351"
    )


def test_111135_richer_source_casualty_report_remains_eligible():
    source = (
        "росіяни атакували Вознесенівський район Запоріжжя. "
        "Влучання у будівлю непрацюючої приватної клініки. "
        "Попередньо, одна людина поранена, тривають рятувальні роботи."
    )
    assert not monitoring_source_context_reason_2351(row(source))


def test_source_with_complete_site_must_not_lose_context_in_its_final():
    source = (
        "Після російського удару по будівлі приватної клініки у "
        "Вознесенівському районі Запоріжжя три людини загинули. "
        "Пожежу рятувальники локалізували."
    )
    incomplete = (
        "В обласній адміністрації повідомили, що загинули троє людей. "
        "Пожежу локалізували."
    )
    complete = (
        "Після удару по приватній клініці у Запоріжжі загинули троє людей. "
        "Рятувальники локалізували пожежу."
    )
    assert not monitoring_source_context_reason_2351(row(source))
    assert monitoring_final_context_issue_2351(row(source), incomplete) == (
        "MONITORING_MISSING_INCIDENT_CONTEXT_IN_FINAL_2351"
    )
    assert not monitoring_final_context_issue_2351(row(source), complete)


def test_111148_5713_individual_memorial_is_not_suppressed():
    memorial = (
        "З глибоким сумом повідомляємо про загибель нашого земляка "
        "Олексія Сідельника. 29 жовтня 2026 року, захищаючи Україну, "
        "загинув старший солдат Сідельник Олексій Вікторович."
    )
    assert not monitoring_source_context_reason_2351(row(memorial))
    assert not monitoring_final_context_issue_2351(
        row(memorial),
        "Захищаючи Україну, загинув старший солдат Олексій Сідельник. "
        "Про це повідомила Оріхівська громада.",
    )


def test_nonfatal_new_local_service_and_normal_regional_news_not_blocked():
    normal = (
        "У Запоріжжі відкрили безоплатний центр підтримки ВПО. "
        "Прийом ведуть щодня з 09:00 до 17:00 на вулиці Перемоги."
    )
    assert not monitoring_source_context_reason_2351(row(normal))
    assert not monitoring_final_context_issue_2351(row(normal), normal)
