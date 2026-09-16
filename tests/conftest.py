from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_channel_outage_test_from_live_provider_probe(request, monkeypatch):
    """Keep the scheduler isolation regression about the scheduler.

    `RuntimeEngine.start()` intentionally launches an asynchronous authenticated AI
    health probe. On Windows release runners an installed Codex SDK can spend a few
    seconds inspecting account state while this unit test has a four-second deadline.
    That external probe is unrelated to the invariant under test: one channel's
    `GatewayExhausted(provider_outage=True)` must not prevent the other channel
    workers from completing.

    Stub only that background probe for this single unit test. Provider probes keep
    their own RC46 regression coverage and remain enabled in production/runtime.
    """
    if request.node.name != "test_runtime_channel_isolation_on_ai_outage":
        return
    monkeypatch.setattr(
        "telegram_autopilot.v2.ai_gateway.AIGateway.probe_all",
        lambda self: [],
    )
