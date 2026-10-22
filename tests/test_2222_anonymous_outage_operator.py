"""Autopilot 2.2.22: exact #74908 LIVE subscriber outage regression.

Operator screenshot + redacted SQLite 2026-10-22, channel ГРОМАДИ:
Zabor ZP https://t.me/zaborzp/155159 source at 17:22 Kyiv, published
17:47:01 Kyiv as Telegram #3511 by installed Autopilot 2.2.21.
"""
from __future__ import annotations

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, Decision
from telegram_autopilot.v2.editorial import (
    EditorialEngine,
    _monitoring_official_context_reject,
    hard_editorial_reject,
    deterministic_monitoring_exclusion,
    prepublish_quality_issues,
)

SOURCE = "🚧⚡️🕯Світло зникло на Осипку, повідомляють підписники"
FINAL = (
    "Світло зникло на Осипку.\n"
    "Підписники повідомляють про відключення електроенергії."
)


def channel(mode=ChannelMode.MONITORING, rules="[LIVE_NOW_RC96] local monitoring"):
    return ChannelConfig(
        id=3,
        name="ЗАПОРІЖЖЯ | ГРОМАДИ",
        telegram_chat_id="-1000",
        mode=mode,
        policy=ChannelPolicy(channel_id=3, rejection_rules=rules),
    )


def article(raw=SOURCE, title=None):
    return {
        "id": 74908,
        "channel_id": 3,
        "source_id": 191,
        "source_name": "ЗаБор Запоріжжя",
        "title": raw if title is None else title,
        "raw_text": raw,
        "source_url": "https://t.me/zaborzp/155159",
        "source_published_at": "2026-10-22T17:22:14+03:00",
    }


def test_exact_operator_74908_rejected_before_ai_at_public_selector():
    item = article()
    ch = channel()
    key = "MONITORING_READER_RUMOR_NOT_OFFICIAL"
    assert key in _monitoring_official_context_reject(item, ch)
    assert key in deterministic_monitoring_exclusion(ch, item)
    result = EditorialEngine.select(object.__new__(EditorialEngine), ch, item)
    assert result.decision == Decision.REJECT
    assert key in result.reason
    assert result.fit_score == 0


def test_old_ready_article_is_rejected_at_final_telegram_gate():
    item = article()
    ch = channel()
    assert "MONITORING_READER_RUMOR_NOT_OFFICIAL" in hard_editorial_reject(ch, item, FINAL)
    assert any(
        "MONITORING_READER_RUMOR_NOT_OFFICIAL" in issue
        for issue in prepublish_quality_issues(ch, item, FINAL)
    )


@pytest.mark.parametrize("raw", [
    SOURCE,
    "Підписники повідомляють: зникло світло на Осипку.",
    "Немає світла у районі, пишуть читачі.",
    "Місцеві мешканці повідомляють, що світла немає.",
    "Баба Галя казала, що вимкнули світло у районі.",
    "Кум сестрі сказав про відключення світла.",
    "У чаті пишуть, що світло зникло.",
])
def test_unsourced_subscriber_neighbor_gossip_is_not_news(raw):
    assert _monitoring_official_context_reject(article(raw), channel()) != ""


@pytest.mark.parametrize("raw", [
    "Світло зникло на Осипку.",
    "У житлових кварталах немає світла.",
    "На Осипку світла немає.",
])
def test_unsourced_power_claims_blocked_even_without_quoted_subscribers(raw):
    assert _monitoring_official_context_reject(article(raw), channel()) == (
        "MONITORING_UNVERIFIED_SERVICE_RUMOR"
    )


def test_anonymous_attribution_in_title_cannot_be_dropped_by_body_extraction():
    item = article("У районі перебої електропостачання.", title=SOURCE)
    assert _monitoring_official_context_reject(item, channel()) == (
        "MONITORING_READER_RUMOR_NOT_OFFICIAL"
    )


@pytest.mark.parametrize("official", [
    "Запоріжжяобленерго повідомило: світло зникло через пошкодження мереж, ремонт триває.",
    "Міська рада підтвердила, що у громаді немає світла через планові роботи.",
    "ОВА повідомила про підтверджені наслідки атаки та пошкодження електромережі.",
    "Малинівська громада завершила реєстрацію на видачу окулярів для ВПО.",
])
def test_real_institutional_claims_are_not_blocked(official):
    assert _monitoring_official_context_reject(article(official), channel()) == ""


def test_other_editorial_channel_not_affected():
    assert hard_editorial_reject(channel(mode=ChannelMode.EDITORIAL), article(), FINAL) == ""
