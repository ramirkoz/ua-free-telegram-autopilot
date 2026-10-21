"""2.2.14: real operator SQLite P0 #210, source-owned monitoring relevance.

Uses exact article source text samples, not editor-generated descriptions or
channel names; tests both first selection and READY pre-publish hard stop.
"""
from __future__ import annotations

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.editorial import (
    hard_editorial_reject, deterministic_monitoring_exclusion, prepublish_quality_issues,
)


def channel(*, opt_in=True, mode=ChannelMode.MONITORING, name="Будь-яка регіональна редакція"):
    return ChannelConfig(
        id=888, name=name, telegram_chat_id="-1000",
        mode=mode,
        policy=ChannelPolicy(
            channel_id=888,
            rejection_rules="[LIVE_NOW_RC96] Інформація про громади" if opt_in else "",
        ),
    )


def article(raw, *, aid=101, source="https://t.me/example/1"):
    return {
        "id":aid, "channel_id":888, "source_id":191,
        "title":raw, "raw_text":raw,
        "source_url":source,"canonical_source_url":source,
    }


JOIN_SPAM = "https://t.me/+UGlLh2-lxcI0NWRi Всі приєдналися? Видаляю через 2 хвилини!"
NONLOCAL_MEME = (
    "Як би Тарас жив у наші часи він би обовязко був би блогером і записував рілси, "
    "вважають тіктокери. Отакі варіанти рілсів з Тарасом, Лесею, Степаном, Іваном."
    "А як ви відноситесь до такого оживлення відомих особистостей за допомогою Ші?"
    " ✉️ https://t.me/zabornews_bot Надіслати новину"
)
MUNICIPAL_QA = (
    "Регіна Харченко відповість на запитання запоріжців під час прямого ефіру. "
    "Очільниця Запорізької міської ради проведе прямий ефір 22 жовтня. "
    "Посадовиця відповідатиме на запитання містян про укриття, безпеку, "
    "школи, дитячі садки, благоустрій і дороги."
)


@pytest.mark.parametrize("raw,reason",[
    (JOIN_SPAM,"MONITORING_PROMO_JOIN_BAIT"),
    (NONLOCAL_MEME,"MONITORING_NONLOCAL_MEME"),
])
def test_operator_negative_examples_rejected_on_all_publication_gates(raw,reason):
    ch=channel()
    row=article(raw)
    assert reason in civic_relevance_exclusion(ch,row)
    assert reason in live_now_exclusion(ch,row)
    assert reason in deterministic_monitoring_exclusion(ch,row)
    # Existing READY final_text created by older v2.2.13 does not override SOURCE.
    assert reason in hard_editorial_reject(ch,row,"Готова редакційна версія")
    assert any(reason in x for x in prepublish_quality_issues(ch,row,"Готовий телеграм-допис без посилань."))


@pytest.mark.parametrize("raw",[
    MUNICIPAL_QA,
    "У Запоріжжі презентували нову виставку AI-рілсів про історичних діячів в міському музеї.",
    "У Василівській громаді організували мистецький фестиваль для дітей.",
    "Запорізька громада запрошує переселенців у чат координації гуманітарної допомоги "
    "https://t.me/+UGlLh2-lxcI0NWRi. Адреси отримання допомоги нададуть координатори.",
    "В укритті Запоріжжя відбудеться зустріч мешканців та презентація проєкту нового "
    "громадського простору. Зареєструватися можна в міському чаті.",
    "У Запорізькій області підтвердили пошкодження 12 будинків внаслідок нічної атаки.",
])
def test_local_community_news_and_events_survive_narrow_negative_gate(raw):
    assert civic_relevance_exclusion(channel(),article(raw)) == ""


def test_source_brand_does_not_create_local_anchor():
    row=article(NONLOCAL_MEME,source="https://t.me/zaborzp/154969")
    assert "MONITORING_NONLOCAL_MEME" in civic_relevance_exclusion(channel(name="Запоріжжя | ГРОМАДИ"),row)


def test_user_opt_in_and_other_channel_isolation():
    for ch in (channel(opt_in=False),channel(mode=ChannelMode.EDITORIAL)):
        assert not civic_relevance_exclusion(ch,article(JOIN_SPAM))
        assert not civic_relevance_exclusion(ch,article(NONLOCAL_MEME))


def test_general_internet_news_not_blanket_blocked():
    raw="У Львові науковці провели дослідження впливу відео TikTok на увагу."
    # A geographically non-local but substantive report isn't silently
    # rejected by high-confidence social-meme patterns alone.
    assert not civic_relevance_exclusion(channel(),article(raw))
