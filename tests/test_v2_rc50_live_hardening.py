from __future__ import annotations

from telegram_autopilot.v2.provider_compat import sanitize_provider_payload
from telegram_autopilot.v2.runtime_hardening import READY_MEDIA_GRACE_SECONDS


def test_groq_gpt_oss_never_sends_invalid_none_reasoning_effort():
    payload = {
        "model": "openai/gpt-oss-120b",
        "reasoning_effort": "none",
        "include_reasoning": True,
        "response_format": {"type": "json_object"},
    }
    clean = sanitize_provider_payload("https://api.groq.com/openai/v1/chat/completions", payload)
    assert clean is not None
    assert clean["reasoning_effort"] == "low"
    assert clean["include_reasoning"] is False
    assert clean["response_format"] == {"type": "json_object"}


def test_groq_qwen_drops_openai_reasoning_controls():
    payload = {
        "model": "qwen/qwen3.8-27b",
        "reasoning_effort": "none",
        "include_reasoning": False,
        "max_completion_tokens": 768,
    }
    clean = sanitize_provider_payload("https://api.groq.com/openai/v1/chat/completions", payload)
    assert clean is not None
    assert "reasoning_effort" not in clean
    assert "include_reasoning" not in clean
    assert clean["max_completion_tokens"] == 768


def test_non_groq_payload_is_not_rewritten():
    payload = {"model": "nvidia/model", "reasoning_effort": "none"}
    assert sanitize_provider_payload("https://integrate.api.nvidia.com/v1/chat/completions", payload) is payload


def test_ready_media_deadlock_has_bounded_grace_window():
    assert READY_MEDIA_GRACE_SECONDS == 1800
