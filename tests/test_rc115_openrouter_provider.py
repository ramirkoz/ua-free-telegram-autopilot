from __future__ import annotations

from pathlib import Path

import telegram_autopilot.v2.provider_api as provider_api
from telegram_autopilot.secrets_store import SecretConfig
from telegram_autopilot.v2.ai_gateway import AIGateway, _rc109_route_slots
from telegram_autopilot.v2.storage import V2Store


def test_rc115_openrouter_requires_explicit_enable_key_and_models(tmp_path: Path) -> None:
    gateway = AIGateway(V2Store(tmp_path / "openrouter.sqlite3"))
    disabled = SecretConfig(openrouter_api_key="sk-or-test", openrouter_models=["openai/gpt-oss-120b"])
    assert gateway._configured("openrouter", disabled) is False

    enabled = SecretConfig(
        openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=["openai/gpt-oss-120b", "google/gemini-2.5-flash"],
    )
    assert gateway._configured("openrouter", enabled) is True
    slots = [slot for slot in gateway._runtime_slots(enabled) if slot.provider == "openrouter"]
    assert [slot.model for slot in slots] == ["openai/gpt-oss-120b", "google/gemini-2.5-flash"]


def test_rc115_openrouter_stays_reserve_even_for_known_direct_model(tmp_path: Path) -> None:
    gateway = AIGateway(V2Store(tmp_path / "routing.sqlite3"))
    cfg = SecretConfig(
        openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=["nvidia/nemotron-3-super-120b-a12b"],
    )
    routed = _rc109_route_slots(gateway._runtime_slots(cfg), "writer")
    direct_idx = next(i for i, slot in enumerate(routed) if slot.provider == "nvidia" and slot.model == "nvidia/nemotron-3-super-120b-a12b")
    openrouter_idx = next(i for i, slot in enumerate(routed) if slot.provider == "openrouter")
    assert direct_idx < openrouter_idx


def test_rc115_actual_openrouter_spend_and_budget_guard(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "budget.sqlite3")
    store.record_ai_usage(
        provider="openrouter",
        model="openai/gpt-oss-120b",
        purpose="writer",
        input_tokens=1000,
        output_tokens=100,
        total_tokens=1100,
        estimated_openrouter_usd=0.0001,
        actual_openrouter_usd=0.42,
    )
    gateway = AIGateway(store)
    cfg = SecretConfig(
        openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=["openai/gpt-oss-120b"],
        openrouter_daily_budget_usd=0.40,
        openrouter_monthly_budget_usd=10.0,
    )
    ok, detail = gateway._openrouter_budget_status(cfg)
    assert ok is False
    assert "budget exhausted" in detail
    summary = store.ai_usage_summary(24)
    assert summary["actual_openrouter_usd"] == 0.42
    assert summary["by_model"][0]["actual_openrouter_usd"] == 0.42


def test_rc115_zero_budget_means_no_cap(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "unlimited.sqlite3")
    store.record_ai_usage(
        provider="openrouter", model="model/x", purpose="writer",
        actual_openrouter_usd=50.0,
    )
    gateway = AIGateway(store)
    cfg = SecretConfig(
        openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=["model/x"],
        openrouter_daily_budget_usd=0.0,
        openrouter_monthly_budget_usd=0.0,
    )
    assert gateway._openrouter_budget_status(cfg)[0] is True


def test_rc115_openrouter_transport_requests_usage_and_reads_actual_cost(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(url, *, headers, payload, timeout_seconds):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return 200, {}, {
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "OK"}}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
                "cost": 0.00123,
            },
        }

    monkeypatch.setattr(provider_api, "_request_json", fake_request)
    reply = provider_api.openai_compatible_chat(
        "openrouter",
        model="openai/gpt-oss-120b",
        api_key="sk-or-test",
        prompt="Return OK",
        max_output_tokens=64,
        timeout_seconds=10,
    )
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["usage"] == {"include": True}
    assert reply.input_tokens == 12
    assert reply.output_tokens == 3
    assert reply.total_tokens == 15
    assert reply.actual_cost_usd == 0.00123
