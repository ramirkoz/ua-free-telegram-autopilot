"""2.3.38: retired model 410/EOL must not retry every six hours.

Pure classification tests. No live provider, Telegram, SQLite or Data changes.
"""
from __future__ import annotations

import pytest

from telegram_autopilot.v2.ai_gateway import _failure_meta
from telegram_autopilot.v2.domain import ProviderState
from telegram_autopilot.v2.provider_api import ProviderAPIError, _classify_http


@pytest.mark.parametrize("error", [
    ProviderAPIError("HTTP 410: model unavailable", kind="model", status=410),
    ProviderAPIError("The model reached end of life", kind="model"),
    ProviderAPIError("This model is no longer available", kind="model", status=404),
    ProviderAPIError("Gone", kind="gone"),
])
def test_retired_model_gets_month_long_model_only_cooldown(error):
    assert _failure_meta(error) == (ProviderState.MODEL_UNSUPPORTED, 30 * 86400, "model")


def test_actual_adapter_classifies_http_410_as_retired():
    error = _classify_http(410, '{"error":"model end of life"}', {})
    assert error.status == 410
    assert _failure_meta(error) == (ProviderState.MODEL_UNSUPPORTED, 30 * 86400, "model")


@pytest.mark.parametrize("error", [
    ProviderAPIError("HTTP 404: model unavailable", kind="model", status=404),
    ProviderAPIError("model_not_found", kind="model"),
])
def test_404_or_unknown_model_retains_six_hour_retry(error):
    assert _failure_meta(error) == (ProviderState.MODEL_UNSUPPORTED, 6 * 3600, "model")


def test_429_remains_rate_limited():
    error = ProviderAPIError("HTTP 429: busy", kind="temporary", status=429, retry_after=90)
    assert _failure_meta(error) == (ProviderState.RATE_LIMIT, 90, "model")


def test_too_large_is_task_scoped():
    error = ProviderAPIError("request too large", kind="request_too_large", status=413)
    assert _failure_meta(error) == (ProviderState.MODEL_UNSUPPORTED, 0, "task")
