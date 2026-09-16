from __future__ import annotations

import pytest

from telegram_autopilot.v2.ai_gateway import PRODUCTION_SLOTS, _failure_meta
from telegram_autopilot.v2.domain import ProviderState
from telegram_autopilot.v2.provider_api import (
    ProviderAPIError,
    _classify_http,
    _extract_openai_text,
    _request_json,
    gemini_generate,
    openai_compatible_chat,
)


def test_provider_transport_rejects_unreviewed_host_before_network() -> None:
    with pytest.raises(ProviderAPIError) as exc:
        _request_json("https://example.com/v1/chat/completions", payload={})
    assert exc.value.kind == "configuration"


def test_reasoning_only_response_is_not_called_network_down() -> None:
    with pytest.raises(ProviderAPIError) as exc:
        _extract_openai_text({
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "", "reasoning": "thinking"}}],
        })
    assert exc.value.kind == "bad_response"
    state, cooldown, scope = _failure_meta(exc.value)
    assert state == ProviderState.UNKNOWN
    assert cooldown == 0
    assert scope == "task"


def test_groq_reasoning_is_bounded_and_json_mode_requested(monkeypatch) -> None:
    captured = {}

    def fake_request(url, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["payload"]
        return 200, {}, {
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "{\"ok\":true}"}}],
        }

    monkeypatch.setattr("telegram_autopilot.v2.provider_api._request_json", fake_request)
    reply = openai_compatible_chat(
        "groq",
        model="openai/gpt-oss-120b",
        api_key="secret",
        prompt="return json",
        max_output_tokens=200,
        timeout_seconds=20,
        json_mode=True,
    )
    assert reply.text == '{"ok":true}'
    assert captured["payload"]["reasoning_effort"] == "low"
    assert captured["payload"]["include_reasoning"] is False
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert "max_completion_tokens" in captured["payload"]


def test_reviewed_groq_slot_uses_current_qwen_generation() -> None:
    groq_models = [slot.model for slot in PRODUCTION_SLOTS if slot.provider == "groq"]
    assert "qwen/qwen3.8-27b" in groq_models
    assert "qwen/qwen3.6-27b" not in groq_models


def test_network_failure_remains_real_network_failure() -> None:
    exc = ProviderAPIError("socket failed", kind="network")
    state, cooldown, scope = _failure_meta(exc)
    assert state == ProviderState.NETWORK_DOWN
    assert cooldown >= 60
    assert scope == "model"


def test_bare_429_is_transient_not_hard_quota() -> None:
    exc = _classify_http(429, '{"error":{"message":"rate limit reached"}}', {"retry-after": "2"})
    assert exc.kind == "temporary"
    assert exc.retry_after == 2


def test_explicit_daily_exhaustion_is_still_quota() -> None:
    exc = _classify_http(429, '{"error":{"message":"requests per day quota reached"}}', {})
    assert exc.kind == "quota"


def test_groq_falls_back_to_20b_after_transient_120b_failure(monkeypatch) -> None:
    attempted = []

    def fake_request(url, **kwargs):
        attempted.append(kwargs["payload"]["model"])
        if kwargs["payload"]["model"] == "openai/gpt-oss-120b":
            raise ProviderAPIError("busy", kind="temporary", status=429, retry_after=2)
        return 200, {}, {
            "model": "openai/gpt-oss-20b",
            "choices": [{"message": {"content": "OK"}}],
        }

    monkeypatch.setattr("telegram_autopilot.v2.provider_api._request_json", fake_request)
    reply = openai_compatible_chat(
        "groq",
        model="openai/gpt-oss-120b",
        api_key="secret",
        prompt="Reply OK",
        max_output_tokens=96,
        timeout_seconds=20,
    )
    assert attempted == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert reply.model == "openai/gpt-oss-20b"
    assert reply.text == "OK"


def test_gemini_falls_back_to_flash_lite_after_transient_failure(monkeypatch) -> None:
    attempted = []

    def fake_request(url, **kwargs):
        attempted.append(url)
        if "gemini-3.5-flash:" in url:
            raise ProviderAPIError("busy", kind="temporary", status=429, retry_after=2)
        return 200, {}, {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
        }

    monkeypatch.setattr("telegram_autopilot.v2.provider_api._request_json", fake_request)
    reply = gemini_generate(
        model="gemini-3.5-flash",
        api_key="secret",
        prompt="Reply OK",
        max_output_tokens=96,
        timeout_seconds=20,
    )
    assert any("gemini-3.5-flash:" in url for url in attempted)
    assert any("gemini-3.5-flash-lite:" in url for url in attempted)
    assert reply.model == "gemini-3.5-flash-lite"
    assert reply.text == "OK"
