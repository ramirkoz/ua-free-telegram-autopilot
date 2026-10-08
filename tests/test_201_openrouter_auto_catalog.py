from __future__ import annotations

import telegram_autopilot.v2.openrouter_catalog as catalog


def test_201_catalog_filters_non_text_and_small_context() -> None:
    payload = {
        "data": [
            {
                "id": "vendor/text-pro",
                "name": "Text Pro",
                "architecture": {"output_modalities": ["text"]},
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "context_length": 64000,
            },
            {
                "id": "vendor/image-pro",
                "name": "Image Pro",
                "architecture": {"output_modalities": ["image"]},
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "context_length": 64000,
            },
            {
                "id": "vendor/tiny-context",
                "name": "Tiny",
                "architecture": {"output_modalities": ["text"]},
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "context_length": 8000,
            },
        ]
    }
    rows = catalog._parse(payload)
    assert [row.id for row in rows] == ["vendor/text-pro"]


def test_201_recommended_models_select_automatically(monkeypatch) -> None:
    rows = (
        catalog.OpenRouterModel("vendor/a-pro", "A Pro", 0.000001, 0.000002, 64000, 3, False),
        catalog.OpenRouterModel("vendor/b-ultra", "B Ultra", 0.000004, 0.000010, 128000, 4, False),
        catalog.OpenRouterModel("vendor/c-mini", "C Mini", 0.0000001, 0.0000002, 32000, 1, False),
    )
    monkeypatch.setattr(catalog, "model_catalog", lambda **kwargs: rows)
    balanced = catalog.recommended_model_ids(strategy="balanced", limit=6)
    quality = catalog.recommended_model_ids(strategy="quality", limit=6)
    assert "vendor/a-pro" in balanced
    assert "vendor/c-mini" not in balanced
    assert quality[0] == "vendor/b-ultra"
