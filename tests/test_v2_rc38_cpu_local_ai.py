from __future__ import annotations

import threading
from types import SimpleNamespace

from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2.domain import ProviderHealth, ProviderState


def _gateway() -> AIGateway:
    gateway = object.__new__(AIGateway)
    gateway.store = SimpleNamespace(
        provider_health=lambda *args: [],
        ai_model_health=lambda *args: [],
        set_provider_health=lambda *args: None,
        set_ai_model_health=lambda *args: None,
        wake_blocked=lambda *args, **kwargs: 0,
    )
    return gateway


def test_local_call_uses_cpu_safe_writer_budget(monkeypatch) -> None:
    gateway = _gateway()
    cfg = SimpleNamespace(local_enabled=True, local_model="qwen3:4b", local_base_url="http://127.0.0.1:8080/v1")
    slot = SimpleNamespace(provider="local", model="local-model", label="local")
    captured = {}

    def fake_generate_local_text(**kwargs):
        captured.update(kwargs)
        return "готовий текст", SimpleNamespace(model="qwen3:4b", label="qwen3:4b / Ollama")

    monkeypatch.setattr("telegram_autopilot.v2.ai_gateway.generate_local_text", fake_generate_local_text)
    text, model, _label = gateway._call_slot(slot, cfg, "x" * 9000, max_output_tokens=1100, timeout_seconds=30)
    assert text == "готовий текст"
    assert model == "qwen3:4b"
    assert captured["max_output_tokens"] == 320
    assert captured["timeout_seconds"] == 240
    assert len(captured["prompt"]) <= 5200


def test_local_call_caps_selection_json_for_cpu_only_notebook(monkeypatch) -> None:
    gateway = _gateway()
    cfg = SimpleNamespace(local_enabled=True, local_model="qwen3:4b", local_base_url="http://127.0.0.1:8080/v1")
    slot = SimpleNamespace(provider="local", model="local-model", label="local")
    captured = {}
    monkeypatch.setattr(
        "telegram_autopilot.v2.ai_gateway.generate_local_text",
        lambda **kwargs: (captured.update(kwargs) or "{}", SimpleNamespace(model="qwen3:4b", label="qwen3:4b / Ollama")),
    )
    gateway._call_slot(slot, cfg, "x" * 5000, max_output_tokens=340, timeout_seconds=25)
    assert captured["max_output_tokens"] == 320
    assert captured["timeout_seconds"] == 240
    assert len(captured["prompt"]) <= 5200


def test_local_health_probe_uses_cpu_timeout(monkeypatch) -> None:
    gateway = _gateway()
    cfg = SimpleNamespace(local_enabled=True, local_model="qwen3:4b", local_base_url="http://127.0.0.1:8080/v1")
    monkeypatch.setattr(gateway, "_configured", lambda provider, _cfg: provider == "local")
    monkeypatch.setattr(gateway, "_provider_slots", lambda provider, _cfg: [SimpleNamespace(provider="local", model="local-model")])
    monkeypatch.setattr(gateway, "_provider_call_lock", lambda provider: threading.Lock())
    captured = {}

    def fake_call(slot, _cfg, prompt, *, max_output_tokens, timeout_seconds):
        captured["budget"] = max_output_tokens
        captured["timeout"] = timeout_seconds
        return "OK", "qwen3:4b", "qwen3:4b / Ollama"

    monkeypatch.setattr(gateway, "_call_slot", fake_call)
    monkeypatch.setattr(gateway, "_mark_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        gateway,
        "_refresh_provider_summary",
        lambda provider, _cfg: ProviderHealth(provider=provider, state=ProviderState.HEALTHY),
    )
    gateway._probe_provider("local", cfg)
    assert captured == {"budget": 48, "timeout": 90}
