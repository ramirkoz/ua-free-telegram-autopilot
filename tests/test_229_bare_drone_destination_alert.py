"""2.2.9 P0: exact operator source zaborzp/154829 must not publish.

This protects monitoring at BOTH deterministic pre-AI and prepublication vetoes,
independent of AI incorrectly labeling a time-sensitive alert as local_news.
"""
import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, Decision
from telegram_autopilot.v2.editorial import EditorialEngine, hard_editorial_reject
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion


def channel(marker: bool = True) -> ChannelConfig:
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-100test",
        mode=ChannelMode.MONITORING, policy=ChannelPolicy(
            channel_id=3,
            rejection_rules="[LIVE_NOW_RC96] Відсів live сигналів" if marker else "",
        ),
    )


def article(text: str) -> dict:
    return {
        "title": text, "raw_text": text,
        "source_name": "Забор Запоріжжя",
        "source_url": "https://t.me/zaborzp/154829",
    }


@pytest.mark.parametrize("text", [
    "🚧👁😡Ланцет на Піски✉️ https://t.me/zabornews_bot Надіслати новину",
    "🚧 Ланцет на Піски",
    "Ланцет у напрямку району",
    "Ланцет над житловою забудовою",
    "FPV на район",
    "БПЛА на околицю",
    "Шахед на місто",
    "КАБ на населений пункт",
])
def test_short_operational_threats_vetoed_before_ai(text):
    reason = hard_editorial_reject(channel(marker=False), article(text))
    assert reason in {"MONITORING_LIVE_ALERT", "POSTFACTUM_ONLY: оперативний сигнал без підтвердженої завершеної події"}


@pytest.mark.parametrize("text", [
    "🚧👁😡Ланцет на Піски✉️ https://t.me/zabornews_bot Надіслати новину",
    "Ланцет у напрямку району",
    "FPV на околицю",
])
def test_opt_in_live_now_redundant_guard(text):
    assert live_now_exclusion(channel(), article(text))


def test_veto_is_before_fake_ai_publish():
    class MustNotRun:
        def run(self, *args, **kwargs):
            raise AssertionError("AI selector must not see operational alert")

    engine = object.__new__(EditorialEngine)
    engine.gateway = MustNotRun()
    result = engine._select_monitoring(
        channel(), article("🚧👁😡Ланцет на Піски✉️ https://t.me/zabornews_bot Надіслати новину")
    )
    assert result.decision == Decision.REJECT
    assert result.fit_score == 0
    assert "MONITORING_LIVE_ALERT" in result.reason


@pytest.mark.parametrize("text", [
    "Після нічної атаки пошкоджено 12 будинків, місцева влада уточнила підсумки.",
    "Ланцет у небі було знищено вночі; за підсумками атаки пошкоджено 12 будинків.",
    "У громаді відкрили новий пункт підтримки.",
    "На виставці представили макет робототехніки для навчання школярів.",
])
def test_concrete_retrospective_or_civil_news_still_allowed(text):
    assert hard_editorial_reject(channel(), article(text)) == ""
    assert live_now_exclusion(channel(), article(text)) == ""


def test_editorial_channels_unaffected():
    ch = channel()
    ch.mode = ChannelMode.EDITORIAL
    assert hard_editorial_reject(ch, article("Ланцет на Піски")) == ""
    assert live_now_exclusion(ch, article("Ланцет на Піски")) == ""
