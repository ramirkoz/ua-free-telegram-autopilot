"""2.2.26 conservative source-owned factual gates.

This module does not claim to perform general semantic entailment. It blocks
only demonstrable source-to-copy safety violations and never uses an AI rewrite
or a neighboring Telegram post as evidence for the original facts.
"""
from __future__ import annotations

from typing import Any
import re

from .editorial_hard_floor import fabricated_event_reason, two_sentence_reason
from .incident_guard import _FATAL_CONTEXT, _FATAL_NUMBER_WORDS
from .claim_verifier import verify_qualified_claims
from .polarity_verifier import verify_source_polarity
from .source_integrity import multi_story_page_cards_reason
from .domain import ChannelMode


def _value(row: Any, name: str) -> str:
    try:
        value = row[name]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, name, "")
    return str(value or "")


def fatality_numbers(value: str) -> frozenset[int]:
    """Numbers explicitly attached to a death/fatality phrase, not random digits.

    Keep every source-mentioned count: an official report may mention both the
    original count and its subsequent correction. Do not conflate wounded,
    buildings or dates with fatalities.
    """
    result: set[int] = set()
    for match in _FATAL_CONTEXT.finditer(str(value or "")):
        token = str(match.group(1) or match.group(2) or "").casefold()
        count = int(token) if token.isdigit() else _FATAL_NUMBER_WORDS.get(token)
        if count is not None:
            result.add(count)
    return frozenset(result)


# A percentage-of-respondents statistic does not, by itself, support a claim
# about how many times more/less frequently every individual performs an action.
# Do not let the writer create new rate multipliers absent from the source.
_MULTIPLIER_RATE = re.compile(
    r"(?iu)\b(?:майже\s+)?(?:у|в)(?:двічі|тричі)\s+"
    r"(?:рідше|частіше|швидше|повільніше)\b"
)
_SOURCE_MULTIPLIER = re.compile(
    r"(?iu)\b(?:удвічі|вдвічі|утричі|втричі|"
    r"twice|tripled|doubled|half\s+as|two[ -]fold|three[ -]fold|"
    r"в\s+два\s+рази|у\s+два\s+рази)\b"
)


def source_fact_issues(article: Any, final_text: str) -> tuple[str, ...]:
    """Guard explicit fatality-count substitutions in any channel.

    Never infer missing numbers: if either side has no explicit count, other
    QA mechanisms handle the statement. This check is not a casualty classifier.
    """
    raw = _value(article, "raw_text").strip() or _value(article, "title").strip()
    source_counts = fatality_numbers(raw)
    outgoing_counts = fatality_numbers(final_text)
    issues: list[str] = []
    if source_counts and outgoing_counts - source_counts:
        issues.append("FACT_UNSUPPORTED_FATALITY_COUNT")
    # Narrow guard for percentage-participation data: a source may report
    # 28% vs 16% of people reading on an average day, which does NOT license
    # an unsourced claim that each person now reads "twice less often".
    if (re.search(r"\d+(?:[.,]\d+)?\s*%", raw)
            and _MULTIPLIER_RATE.search(str(final_text or ""))
            and not _SOURCE_MULTIPLIER.search(raw)):
        issues.append("FACT_UNSUPPORTED_RATE_MULTIPLIER")
    return tuple(issues)


def non_overridable_quality_issues(channel: Any, article: Any, final_text: str) -> tuple[str, ...]:
    """Final publish safety floor, including human-approved and force-publish.

    Human decisions may bypass subjective editorial fit/length preferences,
    but not source provenance, minimum factual content, unjustified certainty,
    claim polarity, manufactured casualties or other high-confidence safety.
    """
    issues: list[str] = []
    for reason in (
        two_sentence_reason(article, final_text),
        fabricated_event_reason(article, final_text),
    ):
        if reason:
            issues.append(reason)
    issues.extend(source_fact_issues(article, final_text))
    if channel.mode == ChannelMode.EDITORIAL:
        reason = multi_story_page_cards_reason(article)
        if reason:
            issues.append(reason)
    if channel.mode == ChannelMode.MONITORING:
        original = _value(article, "raw_text") or _value(article, "title")
        source_id = _value(article, "source_url") or _value(article, "id") or "unknown"
        issues.extend(v.code for v in verify_source_polarity(original, final_text, source_id=source_id))
        issues.extend(v.code for v in verify_qualified_claims(original, final_text, source_id=source_id))
    return tuple(dict.fromkeys(item for item in issues if item))
