"""Source-owned eligible event anchors for monitoring dedupe (2.3.53).

This is a pre-AI comparison rule. A DEDUPED-to-short/REJECT candidate is not
proof that the same event was published. Historic Telegram COMMITTED sources
still count via the published ledger and are never replayed or rewritten.
"""
from __future__ import annotations

from typing import Any

from .domain import ChannelMode, Decision, Stage
from .monitoring_short_material_2352 import (
    _content_text, monitoring_short_material_reason_2352,
)


def _field(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, key, "")
    return str(value or "")


def source_size_2353(row: Any) -> int:
    return len(_content_text(_field(row, "raw_text") or _field(row, "title")))


def eligible_event_anchor_2353(channel: Any, current: Any, candidate: Any) -> bool:
    """Return True only if an uncommitted candidate can safely win dedupe.

    A richer incoming original is allowed to reach the ordinary editor rather
    than being declared a duplicate of a weaker uncommitted record. Later
    prepublish comparison with the durable COMMITTED ledger remains mandatory.
    """
    stage = _field(candidate, "stage")
    decision = _field(candidate, "decision")
    if decision in {str(Decision.REJECT), str(Decision.DUPLICATE)} or stage == str(Stage.ARCHIVED):
        return False
    if stage == str(Stage.PUBLISHED):
        return True
    if getattr(channel, "mode", None) != ChannelMode.MONITORING:
        return True

    if monitoring_short_material_reason_2352(channel, candidate):
        return False

    # A source ruled out by the existing factual/source gates is not a
    # canonical representative of a cluster merely because it arrived first.
    from .editorial import hard_editorial_reject
    from .editorial_hard_floor import two_sentence_reason
    if hard_editorial_reject(channel, candidate) or two_sentence_reason(candidate):
        return False

    if stage not in {str(Stage.READY), str(Stage.QA_PASSED)}:
        current_size = source_size_2353(current)
        previous_size = source_size_2353(candidate)
        if previous_size and current_size >= max(previous_size + 120, int(previous_size * 1.20)):
            return False
    return True


__all__ = ["eligible_event_anchor_2353", "source_size_2353"]
