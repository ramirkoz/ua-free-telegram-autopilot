from __future__ import annotations

"""RC50 live compatibility guard for provider payloads.

Groq's GPT-OSS endpoint accepts reasoning_effort values low/medium/high. RC49 used
"none" for JSON gates, which turned an otherwise healthy provider into a 400 error.
Keep the structured-output hardening, but normalize only the incompatible fields
immediately before transport.
"""

from typing import Any, Mapping

from . import provider_api

_INSTALLED = False
_ORIGINAL_REQUEST_JSON = provider_api._request_json


def sanitize_provider_payload(url: str, payload: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if payload is None or "api.groq.com" not in str(url or "").casefold():
        return payload
    clean = dict(payload)
    model = str(clean.get("model") or "").casefold()
    if "gpt-oss" in model:
        if str(clean.get("reasoning_effort") or "").casefold() not in {"low", "medium", "high"}:
            clean["reasoning_effort"] = "low"
        clean["include_reasoning"] = False
    elif "qwen" in model:
        # Qwen routing does not need the OpenAI-specific reasoning control and
        # Groq may reject unsupported values before the model sees the request.
        clean.pop("reasoning_effort", None)
        clean.pop("include_reasoning", None)
    return clean


def install_provider_compat() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    def guarded_request_json(url: str, **kwargs: Any):
        kwargs["payload"] = sanitize_provider_payload(url, kwargs.get("payload"))
        return _ORIGINAL_REQUEST_JSON(url, **kwargs)

    provider_api._request_json = guarded_request_json
    _INSTALLED = True
