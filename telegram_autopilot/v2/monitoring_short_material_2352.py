"""Regional source admission: no character quota (owner correction 2.3.67).

Historical function names retained for compatibility. Source facts and final QA
remain mandatory; only the arbitrary length gate is superseded.
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


def regional_dispatch_2367(channel: Any) -> bool:
    return (int(getattr(channel, "id", 0) or 0) == REGIONAL_CHANNEL_ID
            and str(getattr(getattr(channel, "mode", None), "value", getattr(channel, "mode", ""))).casefold() == "monitoring")

def regional_publication_floor_2355(channel: Any) -> int:
    """Historical interface; owner superseded the hard length floor in 2.3.67."""
    return 0

def monitoring_short_material_reason_2352(channel: Any, article: Any, text: str = "") -> str:
    if not regional_dispatch_2367(channel):
        return ""
    source = _content_text(_value(article, "raw_text") or _value(article, "title"))
    if not re.search(r"[А-Яа-яІіЇїЄєҐґA-Za-z0-9]", source):
        return "MONITORING_CONTEXT_MISSING"
    return ""


__all__ = ["monitoring_short_material_reason_2352", "regional_publication_floor_2355", "regional_dispatch_2367"]
