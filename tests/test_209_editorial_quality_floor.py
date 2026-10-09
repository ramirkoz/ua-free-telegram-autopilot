from telegram_autopilot.v2 import openrouter_catalog as cat


def _model(mid, quality, price=1.0):
    return cat.OpenRouterModel(
        id=mid, name=mid, prompt_price=price/1_000_000,
        completion_price=price/1_000_000, context_length=128000,
        quality=quality, free=False,
    )


def test_209_editorial_models_require_strong_quality_even_in_economy(monkeypatch):
    monkeypatch.setattr(cat, "model_catalog", lambda force=False: (
        _model("mistralai/mistral-nemo", 2),
        _model("x-ai/grok-4.20-multi-agent", 4),
        _model("nvidia/nemotron-3-super-120b-a12b", 3),
    ))
    for purpose in ("writer", "final_editor", "rewrite", "complex_rewrite"):
        for strategy in ("economy", "balanced", "quality"):
            result = cat.candidate_model_ids_for_task(
                purpose=purpose, strategy=strategy, prompt_chars=3500, max_output_tokens=900,
            )
            assert "mistralai/mistral-nemo" not in result
            assert "x-ai/grok-4.20-multi-agent" not in result
            assert "nvidia/nemotron-3-super-120b-a12b" in result


def test_209_noneditorial_fast_models_remain_eligible(monkeypatch):
    monkeypatch.setattr(cat, "model_catalog", lambda force=False: (
        _model("mistralai/mistral-nemo", 2),
    ))
    assert "mistralai/mistral-nemo" in cat.candidate_model_ids_for_task(
        purpose="editorial_selector", strategy="economy", prompt_chars=1000, max_output_tokens=150,
    )
