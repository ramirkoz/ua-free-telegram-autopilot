from __future__ import annotations

from telegram_autopilot.v2 import openrouter_catalog as cat


def _model(model_id: str, quality: int, price: float = 1.0) -> cat.OpenRouterModel:
    return cat.OpenRouterModel(
        id=model_id, name=model_id, prompt_price=price / 1000000,
        completion_price=price / 1000000, context_length=128000,
        quality=quality, free=False,
    )


def test_208_agentic_model_not_selected_for_automatic_editorial(monkeypatch):
    monkeypatch.setattr(cat, "model_catalog", lambda force=False: (
        _model("x-ai/grok-4.20-multi-agent", 4),
        _model("x-ai/grok-4.20", 4),
        _model("deepseek/deepseek-v4", 3),
    ))
    for task in ("writer", "final_editor", "rewrite", "complex_rewrite"):
        selected = cat.candidate_model_ids_for_task(
            purpose=task, prompt_chars=4800, max_output_tokens=900, strategy="balanced"
        )
        assert "x-ai/grok-4.20-multi-agent" not in selected
        assert "x-ai/grok-4.20" in selected


def test_208_research_route_not_silently_restricted(monkeypatch):
    monkeypatch.setattr(cat, "model_catalog", lambda force=False: (
        _model("x-ai/grok-4.20-multi-agent", 4),
    ))
    assert "x-ai/grok-4.20-multi-agent" in cat.candidate_model_ids_for_task(
        purpose="research", prompt_chars=5000, max_output_tokens=900,
    )
