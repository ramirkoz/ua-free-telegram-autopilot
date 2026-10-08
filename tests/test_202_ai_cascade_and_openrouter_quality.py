from __future__ import annotations

from pathlib import Path

import telegram_autopilot.v2.openrouter_catalog as catalog
from telegram_autopilot.secrets_store import SecretConfig
from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2.storage import V2Store


def test_202_ai_mode_is_downward_only_cascade(tmp_path: Path) -> None:
    gateway = AIGateway(V2Store(tmp_path / "cascade.sqlite3"))

    assert gateway._mode_allows("codex", "codex") is True
    assert gateway._mode_allows("codex", "openrouter") is True
    assert gateway._mode_allows("codex", "gemini") is True

    assert gateway._mode_allows("openrouter", "codex") is False
    assert gateway._mode_allows("openrouter", "openrouter") is True
    assert gateway._mode_allows("openrouter", "gemini") is True

    assert gateway._mode_allows("free", "codex") is False
    assert gateway._mode_allows("free", "openrouter") is False
    assert gateway._mode_allows("free", "gemini") is True


def test_202_openrouter_mode_never_escalates_to_codex(tmp_path: Path) -> None:
    gateway = AIGateway(V2Store(tmp_path / "openrouter.sqlite3"))
    cfg = SecretConfig(
        ai_mode="openrouter",
        openrouter_api_key="sk-or-test",
        codex_enabled=True,  # stale legacy flag must not override canonical mode
        gemini_api_key="g",
    )
    assert gateway._configured("codex", cfg) is False
    assert gateway._configured("openrouter", cfg) is True
    assert gateway._configured("gemini", cfg) is True


def test_202_free_mode_never_escalates_upward(tmp_path: Path) -> None:
    gateway = AIGateway(V2Store(tmp_path / "free.sqlite3"))
    cfg = SecretConfig(
        ai_mode="free",
        openrouter_api_key="sk-or-test",
        openrouter_enabled=True,
        codex_enabled=True,
        gemini_api_key="g",
    )
    assert gateway._configured("codex", cfg) is False
    assert gateway._configured("openrouter", cfg) is False
    assert gateway._configured("gemini", cfg) is True


def test_202_writer_uses_content_tool_strong_to_premium_route() -> None:
    assert catalog.route_tiers("writer", "balanced") == ("strong", "premium")
    assert catalog.route_tiers("final_editor", "balanced") == ("strong", "premium")
    assert catalog.route_tiers("editorial_selector", "balanced") == ("fast_cheap", "strong")


def test_202_writer_does_not_select_quality_two_model(monkeypatch) -> None:
    rows = (
        catalog.OpenRouterModel(
            "mistralai/mistral-nemo", "Mistral Nemo",
            0.0000001, 0.0000002, 128000, 2, False,
        ),
        catalog.OpenRouterModel(
            "vendor/strong-pro", "Strong Pro",
            0.000002, 0.000006, 128000, 3, False,
        ),
        catalog.OpenRouterModel(
            "vendor/premium-ultra", "Premium Ultra",
            0.000008, 0.000020, 200000, 4, False,
        ),
    )
    monkeypatch.setattr(catalog, "model_catalog", lambda **kwargs: rows)

    selected = catalog.candidate_model_ids_for_task(
        purpose="writer",
        prompt_chars=12000,
        max_output_tokens=3000,
        strategy="balanced",
        limit=5,
    )

    assert "mistralai/mistral-nemo" not in selected
    assert selected[0] == "vendor/strong-pro"
