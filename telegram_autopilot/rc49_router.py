from __future__ import annotations

import logging

from .ai_router import AIRouterError

LOG = logging.getLogger("telegram_autopilot.rc49.router")
_INSTALLED = False

_RU_MARKER = "Ты выпускающий редактор Telegram-канала. Это НЕ текст для публикации и не перевод статьи."
_UA_MARKER = "Ти автор українського Telegram-каналу. Напиши фінальний пост З НУЛЯ."


def _route_kwargs(prompt: str, kwargs: dict) -> dict:
    """Return RC49 production-routing overrides without touching diagnostics/LAB."""
    text = str(prompt or "")
    out = dict(kwargs)

    # RC40's old style-score repair is intentionally disabled in RC49. The first
    # UA author either passes hard validation or a fresh candidate is requested;
    # we no longer put safe prose through another generative polishing pass.
    if "RC40 TARGETED COPY-EDIT" in text:
        raise AIRouterError(
            "RC49 keeps the single-author candidate: legacy generative style repair is disabled."
        )

    if text.startswith(_RU_MARKER) or text.startswith(_UA_MARKER):
        out["allowed_providers"] = {"codex", "gemini"}
        skipped = set(out.get("skip_providers") or set())
        skipped.discard("codex")
        skipped.add("local")
        out["skip_providers"] = skipped
        # Do not let a quality-critical unattended writer spend a cycle walking
        # through providers that historically returned mostly errors or drafts
        # later needing another trusted rewrite.
        out["suppress_provider_on_quota"] = False
    return out


def install_rc49_router() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production

    previous = production.run_ai

    def run_ai_rc49(prompt, *args, **kwargs):
        routed = _route_kwargs(str(prompt or ""), kwargs)
        return previous(prompt, *args, **routed)

    production.run_ai = run_ai_rc49
    LOG.info("RC49 production router installed: Codex/Gemini only for story editor and UA author; legacy style repair disabled")
    _INSTALLED = True
