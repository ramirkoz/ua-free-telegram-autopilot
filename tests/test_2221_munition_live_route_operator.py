"""2.2.21: operator LIVE #74814 and safe negative cases.

Source #74814 was a short current aerial-munition movement notice.
AI mistakenly rewrote S8000 "Бандероль" as moving postal parcels.
"""
from __future__ import annotations
import pytest
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.editorial import (
    deterministic_monitoring_exclusion, hard_editorial_reject, prepublish_quality_issues,
)


def channel(opt_in=True, mode=ChannelMode.MONITORING):
    return ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1000",
        mode=mode, policy=ChannelPolicy(channel_id=3,
            rejection_rules="[LIVE_NOW_RC96] regional news" if opt_in else ""))


def article(text, aid=74814):
    return {"id":aid,"channel_id":3,"source_id":191,"title":text,
            "raw_text":text,"source_url":"https://t.me/zaborzp/155137",
            "source_published_at":"2026-10-22T15:57:28+03:00"}


OPERATOR_SOURCE = "🚧🚀🤬Бандероль повз Правобережжя. Через Нове Запоріжжя"
OPERATOR_BAD_FINAL = (
    "🚧 Через Нове Запоріжжя тимчасово перенаправили рух бандеролей, "
    "вони йдуть в об’їзд Правобережжя."
)


def test_operator_74814_must_be_vetoed_before_ai_and_before_send():
    row=article(OPERATOR_SOURCE)
    ch=channel()
    key="MONITORING_LIVE_MUNITION_ROUTE"
    assert key in civic_relevance_exclusion(ch,row)
    assert key in live_now_exclusion(ch,row)
    assert key in deterministic_monitoring_exclusion(ch,row)
    assert key in hard_editorial_reject(ch,row,OPERATOR_BAD_FINAL)
    assert any(key in x for x in prepublish_quality_issues(ch,row,OPERATOR_BAD_FINAL))


@pytest.mark.parametrize("text", [
    "Бандероль повз містом, через район.",
    "Крилата ракета летить у напрямку міста.",
    "Шахед через населені пункти, рух далі.",
    "БПЛА повз місто, у бік іншого населеного пункту.",
])
def test_unsettled_air_threat_routes_are_not_stable_local_news(text):
    assert "MONITORING_LIVE_MUNITION_ROUTE" in civic_relevance_exclusion(channel(),article(text))


@pytest.mark.parametrize("text", [
    "Рятувальники повідомили про пошкодження двох будинків після удару ракети.",
    "Сили ППО збили ракету Бандероль поблизу області, наслідки підтверджені.",
    "Укрпошта запровадила доставку поштових бандеролей через нове відділення.",
    "Відкрито об'їзд місцевої дороги після аварії.",
    "У громаді почав діяти новий соціальний автобусний маршрут.",
])
def test_settled_impact_parcels_and_nonmilitary_events_survive(text):
    assert civic_relevance_exclusion(channel(),article(text)) == ""


def test_gate_stays_off_in_editorial_and_optout():
    for ch in (channel(opt_in=False),channel(mode=ChannelMode.EDITORIAL)):
        assert not civic_relevance_exclusion(ch,article(OPERATOR_SOURCE))
