from __future__ import annotations

"""Runtime compatibility guards for provider payloads and optional Codex SDK startup.

Groq's GPT-OSS endpoint accepts reasoning_effort values low/medium/high. RC49 used
"none" for JSON gates, which turned an otherwise healthy provider into a 400 error.
Keep the structured-output hardening, but normalize only the incompatible fields
immediately before transport.

RC92 also preloads the optional Codex SDK exactly once before V2 worker threads are
started. On Windows the first import of openai_codex pulls in a large Pydantic model
graph; letting several channel workers race through that first import caused a native
0x80000003 process abort in live RC91. The preload is intentionally import-only: it
does not authenticate, start a Codex subprocess, or make a network request.
"""

import importlib
import sys
import threading
from typing import Any, Mapping

from ..codex_engine import codex_extension_dir
from . import provider_api

_INSTALLED = False
_ORIGINAL_REQUEST_JSON = provider_api._request_json
_CODEX_PREWARM_LOCK = threading.Lock()
_CODEX_PREWARMED = False


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
        clean.pop("reasoning_effort", None)
        clean.pop("include_reasoning", None)
    return clean


def prewarm_codex_sdk() -> bool:
    """Import the installed Codex SDK once, synchronously, before runtime fan-out.

    False means Codex is not installed/usable yet. That remains a supported state;
    the normal provider router can continue with other configured providers.
    """
    global _CODEX_PREWARMED
    if _CODEX_PREWARMED:
        return True
    with _CODEX_PREWARM_LOCK:
        if _CODEX_PREWARMED:
            return True
        try:
            extension = codex_extension_dir()
            if not (extension / "openai_codex").exists():
                return False
            value = str(extension)
            if value not in sys.path:
                sys.path.insert(0, value)
            importlib.import_module("openai_codex")
        except Exception:
            return False
        _CODEX_PREWARMED = True
        return True


def install_provider_compat() -> None:
    global _INSTALLED
    if not _INSTALLED:
        def guarded_request_json(url: str, **kwargs: Any):
            kwargs["payload"] = sanitize_provider_payload(url, kwargs.get("payload"))
            return _ORIGINAL_REQUEST_JSON(url, **kwargs)

        provider_api._request_json = guarded_request_json
        _INSTALLED = True

    # This function is called on the main startup thread before RuntimeEngine and
    # its per-channel workers exist. Keep the first heavy Codex import here so no
    # worker can race another worker through Pydantic module construction.
    prewarm_codex_sdk()
