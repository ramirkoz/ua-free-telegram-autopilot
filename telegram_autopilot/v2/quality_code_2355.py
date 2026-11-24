"""Lossless classification of exhausted bounded pre-publication rewrite attempts.

The old rewrite job name `rewrite_oversize` is historical.  Its reason
must not disguise a dangling sentence or failed source grounding as length.
"""
from __future__ import annotations


def terminal_quality_code_2355(error_code: str, detail: str) -> str:
    reason = str(error_code or "").upper()
    explanation = str(detail or "").casefold()
    if reason == "PREPUBLISH_SOURCE_SAFETY":
        return "SOURCE_FACT_QA_BLOCKED"
    if "TRUNCATED_" in reason or any(x in explanation for x in ("обірван", "незавершен", "термінальн")):
        return "PREPUBLISH_TERMINAL_BLOCKED_2355"
    if reason == "PREPUBLISH_QA":
        return "PREPUBLISH_QA_BLOCKED"
    if "OVERSIZE" in reason or any(x in explanation for x in ("надто довг", "понад жорсткий ліміт")):
        return "TELEGRAM_OVERSIZE_BLOCKED"
    return "PREPUBLISH_LENGTH_OR_QUALITY_BLOCKED_2355"


__all__ = ["terminal_quality_code_2355"]
