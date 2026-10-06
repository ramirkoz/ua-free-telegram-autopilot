from __future__ import annotations

from typing import Any


# RC109 discovery is deliberately advisory. It never adds a credential, endpoint,
# model or unattended writer route by itself. Candidates must pass our own QA,
# JSON-compliance, latency, quota and cost checks before they are promoted into
# ai_gateway.PRODUCTION_SLOTS.
_DISCOVERY_SOURCES = (
    {
        "name": "NoPaywall",
        "url": "https://nopaywall.io/",
        "kind": "curated_free_api_catalog",
        "role": "manual_watch",
    },
    {
        "name": "OpenRouter",
        "url": "https://openrouter.ai/models",
        "kind": "model_catalog",
        "role": "manual_watch",
    },
)

_CANDIDATES = (
    {
        "provider": "reflection",
        "model": "Beam",
        "status": "watch",
        "reason": "agentic/reasoning candidate; require stable public API, price, limits and our QA before routing",
        "auto_enable": False,
    },
    {
        "provider": "openrouter",
        "model": "reviewed-free-or-low-cost",
        "status": "candidate_pool",
        "reason": "potential reserve pool; individual model IDs must be reviewed before production routing",
        "auto_enable": False,
    },
)


def provider_discovery_snapshot() -> dict[str, Any]:
    return {
        "mode": "advisory_only",
        "auto_enable": False,
        "sources": [dict(item) for item in _DISCOVERY_SOURCES],
        "candidates": [dict(item) for item in _CANDIDATES],
        "promotion_gates": [
            "stable_api",
            "known_model_id",
            "credential_configured",
            "json_compliance",
            "factual_qa",
            "latency",
            "quota_or_rate_limit",
            "token_usage",
            "cost_per_success",
        ],
        "production_rule": "newly discovered providers/models never become unattended writers automatically",
    }
