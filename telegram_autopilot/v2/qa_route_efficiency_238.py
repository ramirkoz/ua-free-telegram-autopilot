"""v2.2.38: bounded, evidence-preserving local AI output rescue.

Never invent a terminal dot or complete a fragment with guessed facts.
Only remove a short incomplete *last* clause, then run the ORIGINAL complete
article validator again. Numbers, question-vs-assertion, date and source
polarity checks remain authoritative and cannot be bypassed.
"""
from __future__ import annotations

import re


_TRUNCATED_QA = (
    "редакційний qa: незавершене речення або обірваний текст",
    "останнє речення обірване",
)


def clipped_final_clause(error: Exception) -> bool:
    message = str(error or "").casefold()
    return any(key in message for key in _TRUNCATED_QA)


def conservative_completed_tail(text: str, error: Exception) -> str:
    """Return a candidate only when a complete >=2-sentence body survives.

    This function does NOT approve publication. Caller MUST rerun its full QA
    validator, including hard source/claim/polarity checks, after any trim.
    """
    if not clipped_final_clause(error):
        return ""
    source = str(text or "").strip()
    if not source or len(source) > 4000 or len(source) < 180:
        return ""
    if any(source.endswith(mark) for mark in (".", "!", "?", "…")):
        # A grammar/format failure on an otherwise terminated paragraph is
        # not evidence that deleting text is a safe repair.
        return ""
    # Require a real sentence ending, followed by whitespace and a nonempty
    # unfinished clause. Avoid matching decimals and URL fragments.
    stops = list(re.finditer(r"[.!?…][»”'\")\]]*(?=\s+[^\s]|$)", source))
    if not stops:
        return ""
    # When a final quoted sentence ends in punctuation before a closing quote,
    # the whole quote remains attached to its complete sentence.
    end = stops[-1].end()
    kept = source[:end].rstrip()
    tail = source[end:].strip()
    if not tail or len(tail) > 140 or len(tail) > int(len(source) * 0.3):
        return ""
    if len(kept) < 160 or len(stops) < 2:
        return ""
    if any(re.search(r"\b(?:https?://|www\.)", part, re.I) for part in (kept[-140:], tail)):
        # Last-clause URL truncations are ambiguous: do not trim in ways that
        # could obscure mandatory clickable public-service details.
        return ""
    return kept


def suppress_reasoning_only_route(provider: str, error: Exception) -> bool:
    """One-cycle Cloudflare opt-out after reasoning-only (no final) failure.

    The very next job may retry; persisted provider/model health and operator
    configuration are unchanged. Never suppress other models or outages.
    """
    return (
        str(provider or "").casefold() == "cloudflare"
        and str(getattr(error, "kind", "") or "").casefold() == "bad_response"
        and "reasoning but no final content" in str(error).casefold()
    )


def bounded_local_timeout(requested: int, *, caller_timeout: int) -> int:
    """Prevent an unproductive CPU fallback from monopolizing a worker 300s."""
    return min(max(40, int(requested)), max(120, 4 * max(8, int(caller_timeout))))
