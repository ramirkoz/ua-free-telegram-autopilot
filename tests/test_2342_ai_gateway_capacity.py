"""2.3.42 LIVE concurrency regressions. Never send API/Telegram requests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic, sleep
from types import SimpleNamespace
import inspect

import pytest

from telegram_autopilot import ai_router as legacy_ai
import telegram_autopilot.v2.ai_gateway as module
from telegram_autopilot.v2.ai_gateway import AIGateway, GatewayExhausted
from telegram_autopilot.v2.domain import ProviderHealth
from telegram_autopilot.v2.storage import V2Store


def test_openrouter_has_three_bounded_parallel_slots_shared_between_gateways(tmp_path):
    a = AIGateway(V2Store(tmp_path / "a.sqlite3"))
    b = AIGateway(V2Store(tmp_path / "b.sqlite3"))
    gate = a._provider_call_lock("openrouter")
    assert gate is b._provider_call_lock("openrouter")
    acquired = 0
    try:
        for _ in range(3):
            assert gate.acquire(blocking=False), "Expected capacity for three workers"
            acquired += 1
        assert not gate.acquire(blocking=False), "Fourth request must queue"
        other = a._provider_call_lock("groq")
        assert other.acquire(blocking=False), "Other providers remain independent"
        try:
            assert not other.acquire(blocking=False), "Groq single-call conservative cap retained"
        finally:
            other.release()
    finally:
        for _ in range(acquired):
            gate.release()


def test_real_gateway_admits_three_simultaneous_openrouter_calls(tmp_path, monkeypatch):
    """Exercise AIGateway.run, not just the semaphore, without network traffic."""
    store = V2Store(tmp_path / "parallel.sqlite3")
    gateway = AIGateway(store)
    cfg = SimpleNamespace(ai_mode="openrouter")
    slot = legacy_ai.Slot(1, "openrouter", "test/model", "Test route")
    monkeypatch.setattr(module, "load_secrets", lambda: cfg)
    monkeypatch.setattr(gateway, "_runtime_slots", lambda cfg: [])
    monkeypatch.setattr(gateway, "_openrouter_task_slots", lambda cfg, **kw: [slot])
    monkeypatch.setattr(gateway, "_configured", lambda provider, cfg: provider == "openrouter")
    monkeypatch.setattr(gateway, "_provider_blocked", lambda provider: False)
    monkeypatch.setattr(gateway, "_model_blocked", lambda provider, model: False)
    monkeypatch.setattr(gateway, "_openrouter_budget_status", lambda cfg: (True, ""))
    monkeypatch.setattr(gateway, "_mark_success", lambda *args: None)
    monkeypatch.setattr(gateway, "_refresh_provider_summary",
                        lambda provider, cfg: ProviderHealth(provider=provider))
    monkeypatch.setattr(store, "record_ai_usage", lambda **kw: None)

    current = [0]
    peak = [0]
    monitor = Lock()

    def fake_call(slot, cfg, prompt, **kwargs):
        with monitor:
            current[0] += 1
            peak[0] = max(peak[0], current[0])
        try:
            sleep(0.3)
            return ("Перевірка пройдена.", slot.model, slot.label, 15, 8, 23)
        finally:
            with monitor:
                current[0] -= 1

    monkeypatch.setattr(gateway, "_call_slot", fake_call)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda i: gateway.run(
            f"Story {i}", purpose="writer", max_output_tokens=250,
            timeout_seconds=25), range(3)))
    assert peak[0] == 3, "OpenRouter models must not serialize behind one global lock"
    assert len(results) == 3
    assert all(result.provider == "openrouter" for result in results)


def test_health_probe_never_waits_in_front_of_live_editors(tmp_path, monkeypatch):
    gateway = AIGateway(V2Store(tmp_path / "probe.sqlite3"))
    cfg = SimpleNamespace(ai_mode="openrouter")
    slot = legacy_ai.Slot(1, "openrouter", "test/model", "Probe candidate")
    monkeypatch.setattr(gateway, "_configured", lambda provider, cfg: True)
    monkeypatch.setattr(gateway, "_provider_slots", lambda provider, cfg: [slot])
    monkeypatch.setattr(gateway, "_openrouter_budget_status", lambda cfg: (True, ""))
    monkeypatch.setattr(gateway, "_refresh_provider_summary",
                        lambda provider, cfg: ProviderHealth(provider=provider))
    calls = []
    monkeypatch.setattr(gateway, "_call_slot", lambda *a, **kw: calls.append(1))
    gate = gateway._provider_call_lock("openrouter")
    acquired = 0
    try:
        for _ in range(3):
            assert gate.acquire(blocking=False)
            acquired += 1
        started = monotonic()
        result = gateway._probe_provider("openrouter", cfg)
        elapsed = monotonic() - started
        assert result.provider == "openrouter"
        assert elapsed < 0.5, "Probe should skip occupied capacity without 2s+ blocking"
        assert not calls, "Probe must never call API while three workers hold capacity"
    finally:
        for _ in range(acquired):
            gate.release()


def test_capacity_is_not_an_article_quality_or_provider_outage():
    exc = GatewayExhausted("Capacity queue saturated", provider_outage=False,
                           congested=True, retry_seconds=30)
    assert exc.congested and not exc.provider_outage
    runtime = inspect.getsource(__import__(
        "telegram_autopilot.v2.runtime", fromlist=["V2Runtime"]))
    assert 'code = ("AI_CAPACITY_WAIT"' in runtime
    assert "count_attempt=not ai_wait" in runtime
    assert "if not ai_wait and attempts >=" in runtime


def test_paid_attempt_is_charged_only_after_admission():
    code = inspect.getsource(AIGateway.run)
    assert code.index("acquired = lock.acquire(timeout=wait_for_lock)") < code.index(
        "paid_attempts_232 += 1")
    assert "paid_attempt_charged=False" in code
    assert "congested=True" in code
    assert "provider_outage=False" in code
