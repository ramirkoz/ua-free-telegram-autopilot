from __future__ import annotations

from pathlib import Path

import telegram_autopilot.v2.provider_api as provider_api
import telegram_autopilot.v2.ai_gateway as ai_gateway
from telegram_autopilot.secrets_store import SecretConfig
from telegram_autopilot.v2.ai_gateway import AIGateway, _rc109_route_slots
from telegram_autopilot.v2.storage import V2Store


def test_201_openrouter_requires_enable_and_key_but_not_manual_models(tmp_path: Path, monkeypatch) -> None:
    gateway = AIGateway(V2Store(tmp_path / "openrouter.sqlite3"))
    disabled = SecretConfig(openrouter_api_key="sk-or-test")
    assert gateway._configured("openrouter", disabled) is False

    enabled = SecretConfig(
        ai_mode="openrouter",
        openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=[],
        openrouter_strategy="balanced",
    )
    assert gateway._configured("openrouter", enabled) is True
    monkeypatch.setattr(
        ai_gateway,
        "candidate_model_ids_for_task",
        lambda **kwargs: ("openai/gpt-oss-120b", "google/gemini-2.5-flash"),
    )
    slots = gateway._openrouter_task_slots(
        enabled, purpose="writer", prompt_chars=5000, max_output_tokens=2000
    )
    assert [slot.model for slot in slots] == ["openai/gpt-oss-120b", "google/gemini-2.5-flash"]


def test_201_openrouter_manual_models_remain_advanced_override(tmp_path: Path, monkeypatch) -> None:
    gateway = AIGateway(V2Store(tmp_path / "manual.sqlite3"))
    cfg = SecretConfig(
        ai_mode="openrouter",
        openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=["manual/model-x"],
    )
    monkeypatch.setattr(ai_gateway, "recommended_model_ids", lambda **kwargs: ("auto/model-y",))
    slots = gateway._openrouter_task_slots(
        cfg, purpose="writer", prompt_chars=5000, max_output_tokens=2000
    )
    assert [slot.model for slot in slots] == ["manual/model-x"]


def test_202_openrouter_mode_orders_openrouter_before_free_fallback(tmp_path: Path, monkeypatch) -> None:
    gateway = AIGateway(V2Store(tmp_path / "routing.sqlite3"))
    cfg = SecretConfig(
        ai_mode="openrouter",
        openrouter_api_key="sk-or-test",
        openrouter_models=["manual/strong-model"],
        nvidia_api_key="nv-test",
    )
    openrouter_slots = gateway._openrouter_task_slots(
        cfg, purpose="writer", prompt_chars=8000, max_output_tokens=2500
    )
    free_slots = [
        slot for slot in _rc109_route_slots(gateway._runtime_slots(cfg), "writer")
        if slot.provider in {"gemini", "nvidia", "groq", "cloudflare", "local"}
    ]
    routed = openrouter_slots + free_slots
    assert routed[0].provider == "openrouter"
    assert any(slot.provider == "nvidia" for slot in routed[1:])


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
