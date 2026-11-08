"""2.3.19 operator OpenRouter-only, source-scope and copy regressions."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import telegram_autopilot.v2.ai_gateway as routes
from telegram_autopilot.ai_router import Slot
from telegram_autopilot.ukrainian_quality import (
    apply_safe_ukrainian_fixes, final_language_blockers,
)
from telegram_autopilot.v2.ai_gateway import AIGateway, GatewayExhausted, PRODUCTION_SLOTS
from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, ChannelPolicy, ProviderState,
)
from telegram_autopilot.v2.monitoring_source_scope_2317 import (
    monitoring_source_scope_reason_2317,
)
from telegram_autopilot.v2.editorial_source_topic_2319 import (
    editorial_source_topic_reason_2319,
)
from telegram_autopilot.v2.provider_api import ProviderAPIError


def _gateway(monkeypatch, mode="openrouter", budget=True):
    gateway = AIGateway.__new__(AIGateway)
    usage = []
    gateway.store = SimpleNamespace(record_ai_usage=lambda **kw: usage.append(kw))
    cfg = SimpleNamespace(ai_mode=mode, openrouter_api_key="not-a-real-key")
    monkeypatch.setattr(routes, "load_secrets", lambda: cfg)
    monkeypatch.setattr(gateway, "_runtime_slots", lambda config: [
        Slot(1, "gemini", "gemini-test", "Gemini direct")
    ])
    monkeypatch.setattr(gateway, "_openrouter_task_slots", lambda *a, **kw: [
        Slot(21, "openrouter", "or-model-a", "OpenRouter A"),
        Slot(22, "openrouter", "or-model-b", "OpenRouter B"),
    ])
    monkeypatch.setattr(gateway, "_configured", lambda provider, config: True)
    monkeypatch.setattr(gateway, "_openrouter_budget_status", lambda config: (budget, "budget"))
    monkeypatch.setattr(gateway, "_mark_openrouter_budget_block", lambda config: None)
    monkeypatch.setattr(gateway, "_provider_blocked", lambda provider: False)
    monkeypatch.setattr(gateway, "_model_blocked", lambda provider, model: False)
    monkeypatch.setattr(gateway, "_mark_success", lambda *a, **kw: None)
    monkeypatch.setattr(gateway, "_mark_task_failure", lambda *a, **kw: None)
    monkeypatch.setattr(gateway, "_refresh_provider_summary",
                        lambda provider, config: SimpleNamespace(state=ProviderState.HEALTHY))
    return gateway, usage


@pytest.mark.parametrize("purpose", [
    "writer", "final_editor", "rewrite", "editorial_selector", "monitoring_selector",
])
def test_2319_openrouter_exclusive_for_every_ai_purpose(monkeypatch, purpose):
    gateway, usage = _gateway(monkeypatch)
    attempted = []

    def generate(slot, cfg, prompt, **kwargs):
        attempted.append(slot.provider)
        return ("готовий текст", slot.model, slot.label, 2, 2, 4)

    monkeypatch.setattr(gateway, "_call_slot", generate)
    answer = gateway.run("Тест джерела і редакції", purpose=purpose)
    assert answer.provider == "openrouter"
    assert attempted == ["openrouter"], (purpose, attempted)
    assert len(usage) == 1


def test_2319_bad_openrouter_text_tries_next_openrouter_not_free(monkeypatch):
    gateway, _ = _gateway(monkeypatch)
    attempted = []

    def generate(slot, cfg, prompt, **kwargs):
        attempted.append(slot.provider + ":" + slot.model)
        return ("помилка" if slot.model == "or-model-a" else "перевірено",
                slot.model, slot.label, 5, 5, 10)

    monkeypatch.setattr(gateway, "_call_slot", generate)

    def validate(text):
        if text != "перевірено":
            raise ValueError("Fact Guard: непідтверджений факт")

    assert gateway.run("Тест", purpose="writer", validator=validate).provider == "openrouter"
    assert attempted == ["openrouter:or-model-a", "openrouter:or-model-b"]


def test_2319_both_openrouter_models_fail_qa_without_free_route(monkeypatch):
    gateway, _ = _gateway(monkeypatch)
    called = []

    def generate(slot, cfg, prompt, **kwargs):
        called.append(slot.provider)
        return ("невалідно", slot.model, slot.label, 5, 5, 10)

    monkeypatch.setattr(gateway, "_call_slot", generate)

    def reject(text):
        raise ValueError("Fact Guard: вигадане твердження")

    with pytest.raises(GatewayExhausted) as error:
        gateway.run("Тест", purpose="writer", validator=reject)
    assert error.value.provider_outage is False
    assert called == ["openrouter", "openrouter"]


def test_2319_emergency_direct_only_after_shared_openrouter_network_outage(monkeypatch):
    gateway, _ = _gateway(monkeypatch)
    attempted = []

    def generate(slot, cfg, prompt, **kwargs):
        attempted.append(slot.provider)
        if slot.provider == "openrouter":
            raise ProviderAPIError("DNS resolution failed for openrouter.ai", kind="network")
        return ("резерв працює", slot.model, slot.label, 5, 5, 10)

    monkeypatch.setattr(gateway, "_call_slot", generate)
    monkeypatch.setattr(gateway, "_mark_model_failure",
                        lambda provider, model, exc: (ProviderState.NETWORK_DOWN, "model"))
    answer = gateway.run("Тест аварії", purpose="writer")
    assert answer.provider == "gemini"
    assert attempted == ["openrouter", "openrouter", "gemini"]


def test_2319_budget_exhausted_allows_emergency_direct(monkeypatch):
    gateway, _ = _gateway(monkeypatch, budget=False)
    calls = []
    def generate(slot, cfg, prompt, **kwargs):
        calls.append(slot.provider)
        return ("резерв працює", slot.model, slot.label, 2, 2, 4)
    monkeypatch.setattr(gateway, "_call_slot", generate)
    assert gateway.run("Тест", purpose="writer").provider == "gemini"
    assert calls == ["gemini"]


def test_2319_cloudflare_slot_is_gemma_backup_not_deprecated_nemotron():
    rows = [(slot.provider, slot.model) for slot in PRODUCTION_SLOTS]
    assert ("cloudflare", "@cf/google/gemma-4-26b-a4b-it") in rows
    assert ("cloudflare", "@cf/nvidia/nemotron-3-120b-a12b") not in rows


def _monitoring():
    return ChannelConfig(
        id=3, name="ГРОМАДИ", telegram_chat_id="-100333",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]"),
    )


def test_2319_lunch_greeting_not_an_initiative():
    article = {"title": "Маєте ідеї до обіду?",
               "raw_text": "Всім смачного! Діліться варіантами обіду."}
    assert monitoring_source_scope_reason_2317(_monitoring(), article) == (
        "MONITORING_SOCIAL_GREETING_NOT_NEWS_2319"
    )


@pytest.mark.parametrize("title,body,expected", [
    ("Зустріч в Абу-Дабі", "В Абу-Дабі пройшли дипломатичні переговори делегацій.",
     "MONITORING_NONLOCAL_DIPLOMACY_2319"),
    ("Трагедія на Черкащині", "На Черкащині загинули військові медики.",
     "MONITORING_NONLOCAL_CHERKASY_EVENT_2319"),
    ("Вербування в Центральній Азії", "У Центральній Азії вербують найманців до армії.",
     "MONITORING_NONLOCAL_CENTRAL_ASIA_2319"),
])
def test_2319_gromady_remote_event_requires_local_source_link(title, body, expected):
    assert monitoring_source_scope_reason_2317(
        _monitoring(), {"title": title, "raw_text": body}
    ) == expected
    assert monitoring_source_scope_reason_2317(
        _monitoring(), {"title": title, "raw_text": body + " Це стосується Запоріжжя."}
    ) == ""


def test_2319_real_local_civic_event_and_national_aid_still_allowed():
    assert not monitoring_source_scope_reason_2317(_monitoring(), {
        "title": "Безкоштовний обід для переселенців",
        "raw_text": "У Запоріжжі відкрили пункт безкоштовного харчування для ВПО. Всім смачного!",
    })
    assert not monitoring_source_scope_reason_2317(_monitoring(), {
        "title": "Допомога для ВПО",
        "raw_text": "В Україні оновили субсидії для переселенців з усіх регіонів, зокрема Запоріжжя.",
    })


def test_2319_science_rejects_actual_wired_vacation_advice(monkeypatch):
    import telegram_autopilot.v2.editorial_source_topic_2319 as scope
    monkeypatch.setattr(scope, "calibrated_editorial_role", lambda channel: "science")
    channel = SimpleNamespace(mode=ChannelMode.EDITORIAL)
    assert scope.editorial_source_topic_reason_2319(channel, {
        "title": "How to Remind Your Boss About Your Vacation",
    }) == "SCIENCE_NONTECH_WORKPLACE_ADVICE_2319"
    assert scope.editorial_source_topic_reason_2319(channel, {
        "title": "New AI Tool Improves Satellite Weather Forecasts",
    }) == ""


@pytest.mark.parametrize("original,repaired", [
    ("У середмісті Запоріжжі відкрили виставку.", "У середмісті Запоріжжя відкрили виставку."),
    ("У парку всесохли берези.", "У парку висохли берези."),
    ("У місті налічують 37 парків і сквери.", "У місті налічують 37 парків і скверів."),
    ("Поки не підтвердилося його загибель.", "Поки не підтвердилася його загибель."),
    ("Він розміром з індіку.", "Він розміром з індика."),
])
def test_2319_fixes_attested_ukrainian_not_facts(original, repaired):
    assert apply_safe_ukrainian_fixes(original) == repaired
    assert not final_language_blockers(repaired)


def test_2319_bulb_semantic_contradiction_fails_closed():
    assert final_language_blockers(
        "Пристрій дає змогу змінювати джерело світла без потреби замінювати саму лампу."
    )
