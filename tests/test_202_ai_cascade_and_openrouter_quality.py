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


def test_204_openrouter_excludes_batch_only_models_from_live_and_cached_catalog(monkeypatch) -> None:
    rows = (
        catalog.OpenRouterModel("openai/gpt-oss-120b:batch", "Batch only", 0.0000001, 0.0000001, 128000, 3, False),
        catalog.OpenRouterModel("openai/gpt-oss-120b", "Chat compatible", 0.0000002, 0.0000003, 128000, 3, False),
    )
    monkeypatch.setattr(catalog, "model_catalog", lambda **kwargs: rows)
    selected = catalog.candidate_model_ids_for_task(
        purpose="writer", prompt_chars=9000, max_output_tokens=2000, strategy="balanced",
    )
    assert "openai/gpt-oss-120b:batch" not in selected
    assert "openai/gpt-oss-120b" in selected
    assert catalog._chat_compatible_id("openai/gpt-oss-120b:batch") is False


def test_204_codex_quota_retry_duration_seconds() -> None:
    from telegram_autopilot.v2.ai_gateway import _codex_retry_after_seconds

    assert 340 <= _codex_retry_after_seconds("Please try again in 4m41.232s") <= 390
    assert 3600 <= _codex_retry_after_seconds("Retry after 1h 15m") <= 4700
    assert _codex_retry_after_seconds("unrelated error") == 0


def test_204_codex_quota_retry_iso_reset() -> None:
    from datetime import datetime, timedelta, timezone
    from telegram_autopilot.v2.ai_gateway import _codex_retry_after_seconds

    reset_at = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(timespec="seconds")
    seconds = _codex_retry_after_seconds(f"usage limit resets at {reset_at}")
    assert 1190 <= seconds <= 1350


def test_205_editorial_prefers_quality_over_cheapest_model(monkeypatch) -> None:
    rows = (
        catalog.OpenRouterModel("vendor/cheap-strong", "Cheap Strong", 0.0000001, 0.0000001, 128000, 3, False),
        catalog.OpenRouterModel("vendor/premium-editor", "Premium Editor", 0.000004, 0.000008, 128000, 4, False),
    )
    monkeypatch.setattr(catalog, "model_catalog", lambda **kwargs: rows)
    for purpose in ("writer", "final_editor"):
        selected = catalog.candidate_model_ids_for_task(
            purpose=purpose, prompt_chars=5000, max_output_tokens=1600, strategy="balanced", limit=2,
        )
        assert selected[0] == "vendor/premium-editor", selected


def test_205_editorial_does_not_change_selector_economics(monkeypatch) -> None:
    rows = (
        catalog.OpenRouterModel("vendor/cheap", "Cheap", 0.0000001, 0.0000001, 128000, 3, False),
        catalog.OpenRouterModel("vendor/premium", "Premium", 0.000004, 0.000008, 128000, 4, False),
    )
    monkeypatch.setattr(catalog, "model_catalog", lambda **kwargs: rows)
    selected = catalog.candidate_model_ids_for_task(
        purpose="editorial_selector", prompt_chars=2000, max_output_tokens=120, strategy="balanced", limit=2,
    )
    assert selected[0] == "vendor/cheap"
