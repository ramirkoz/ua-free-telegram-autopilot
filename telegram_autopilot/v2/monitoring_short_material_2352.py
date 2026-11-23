"""Fail-closed regional source and final length floor, owner editorial rule.

A source with too few confirmed facts is not made publishable by an AI
rewriter. The minimum 500-character source/final policy is only for the
regional news channel; never alter CTRL+UA or ПРОДАНО!.

Applied in hard_editorial_reject before AI and before Telegram, including
previously READY items, so no legacy short post can bypass it.
"""
from __future__ import annotations

import re
from typing import Any


REGIONAL_CHANNEL_ID = 3
MIN_REGIONAL_NEWS_CHARS = 500


def _value(article: Any, key: str) -> str:
    try:
        v = article[key]
    except (KeyError, TypeError, IndexError):
        v = getattr(article, key, "")
    return str(v or "")


def _content_text(text: str) -> str:
    # URL, Telegram markup and emojis are not evidence of a complete story.
    clean = re.sub(r"https?://\S+|(?:t\.me/|www\.)\S+", " ", str(text or ""), flags=re.I)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def monitoring_short_material_reason_2352(channel: Any, article: Any, text: str = "") -> str:
    if (int(getattr(channel, "id", 0) or 0) != REGIONAL_CHANNEL_ID
            or str(getattr(getattr(channel, "mode", None), "value", getattr(channel, "mode", ""))).casefold()
            != "monitoring"):
        return ""

    # At least the actual configured threshold; never silently downgrade it
    # to 20/85/270 characters because the original was short.
    policy = getattr(channel, "policy", None)
    min_chars = max(MIN_REGIONAL_NEWS_CHARS, int(getattr(policy, "target_min_chars", 0) or 0))

    source = _content_text(_value(article, "raw_text") or _value(article, "title"))
    if len(source) < min_chars:
        return "MONITORING_SHORT_SOURCE_DROP_2352"

    # Do not force any text to be padded to 500. Let the existing AI writer
    # use only supported facts; when its faithful answer is too short,
    # REJECT instead of publishing or inventing an extension.
    if text and len(_content_text(text)) < min_chars:
        return "MONITORING_SHORT_FINAL_DROP_2352"
    return ""


__all__ = ["monitoring_short_material_reason_2352"]
