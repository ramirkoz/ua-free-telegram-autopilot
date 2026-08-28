from __future__ import annotations

import pytest

from telegram_autopilot.ai_router import AIRouterError
from telegram_autopilot.rc49_router import _route_kwargs


def test_story_editor_uses_trusted_cloud_route_and_removes_codex_skip():
    routed = _route_kwargs(
        "Ты выпускающий редактор Telegram-канала. Это НЕ текст для публикации и не перевод статьи.\nSOURCE",
        {"allowed_providers": {"gemini", "groq", "nvidia", "cloudflare", "local"}, "skip_providers": {"codex"}},
    )
    assert routed["allowed_providers"] == {"codex", "gemini"}
    assert "codex" not in routed["skip_providers"]
    assert "local" in routed["skip_providers"]


def test_ua_author_uses_codex_or_gemini_only():
    routed = _route_kwargs(
        "Ти автор українського Telegram-каналу. Напиши фінальний пост З НУЛЯ.\nSOURCE",
        {"allowed_providers": {"groq", "nvidia"}},
    )
    assert routed["allowed_providers"] == {"codex", "gemini"}
    assert "local" in routed["skip_providers"]


def test_legacy_generative_style_repair_is_disabled():
    with pytest.raises(AIRouterError):
        _route_kwargs(
            "Ти автор українського Telegram-каналу. Напиши фінальний пост З НУЛЯ.\n\nRC40 TARGETED COPY-EDIT.",
            {},
        )


def test_unrelated_diagnostics_routing_is_untouched():
    original = {"allowed_providers": {"nvidia"}, "skip_providers": {"local"}}
    routed = _route_kwargs("diagnostic prompt", original)
    assert routed == original
