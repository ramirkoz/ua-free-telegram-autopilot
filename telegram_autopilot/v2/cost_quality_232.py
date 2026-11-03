"""2.3.2: bounded paid AI routes and strictly form-only output repair.

No source text or claim modifications. Every proposed repair goes through original
full article validator; unsafe fact claims still fail closed.
"""
from __future__ import annotations

import re

EXPENSIVE_DEFAULT_MODELS = frozenset({"x-ai/grok-4.20", "x-ai/grok-4.20-multi-agent"})
PAID_EDITORIAL_PURPOSES = frozenset({"writer", "final_editor", "rewrite", "complex_rewrite"})


def order_openrouter_editorial_models(models: tuple[str, ...], *, manual: bool) -> tuple[str, ...]:
    """Treat Grok as last-resort only for automatic editorial routing."""
    if manual:
        return models  # explicit operator order remains authoritative
    return tuple(sorted(models, key=lambda m: (str(m).casefold() in EXPENSIVE_DEFAULT_MODELS,)))


def safe_format_candidate(text: str, error: Exception) -> str:
    """Candidate-only whitespace/source-footer repair; never blesses publication."""
    source = str(text or "").strip()
    reason = str(error or "").casefold()
    if not (180 <= len(source) <= 4000):
        return ""
    if "source-body qa" in reason and ("дублює footer" in reason or "duplicates footer" in reason):
        # Only remove a trailing source-attribution URL; no other URL or factual
        # prose may be removed. Full QA is mandatory after this operation.
        match = re.search(r"(?iu)(?:\s+(?:джерело\s*[:：]|source\s*[:：]|читати\s*[:：])\s*)https?://[^\s]+\s*$", source)
        if match:
            cleaned = source[:match.start()].rstrip()
            if len(cleaned) >= 170 and cleaned[-1:] in ".!?…»”":
                return cleaned
    if "суцільна стіна тексту без абзаців" in reason and "\n" not in source:
        # Add ONLY whitespace at an existing sentence boundary. A period after
        # abbreviations/URLs may be unsafe, therefore require substantive sides.
        stops = [m.end() for m in re.finditer(r"[.!?…](?:[»”\"']?)(?=\s+[А-ЯІЇЄҐ])", source)]
        options = [p for p in stops if p >= 140 and len(source) - p >= 140]
        if options:
            p = min(options, key=lambda i: abs(i - len(source) / 2))
            return source[:p].rstrip() + "\n\n" + source[p:].lstrip()
    return ""

_CIVIC_SERVICE = re.compile(r"(?iu)\b(?:євідновлення|компенсаці\w*|цнап|пошкоджен\w*\s+житл\w*)\b")
_CIVIC_ACTION = re.compile(r"(?iu)\b(?:подати\s+заяв\w*|звернут\w*|через\s+дію|отримати\s+компенсаці\w*|як\s+отримати|як\s+діяти)\b")
_IMMEDIATE_ALERT = re.compile(r"(?iu)\b(?:зараз|наразі|щойно|прямо\s+зараз|повітрян\w*\s+тривог\w*|летить|проліта\w*|курсом\s+на|рухає\w*\s+у\s+напрямку|у\s+напрямку|в\s+напрямку|пуск\w*\s+ракет\w*)\b")

def civic_guidance_not_live_alert(source: str) -> bool:
    text = str(source or "").casefold()
    return (len(text) >= 280 and bool(_CIVIC_SERVICE.search(text))
            and bool(_CIVIC_ACTION.search(text))
            and not bool(_IMMEDIATE_ALERT.search(text)))
