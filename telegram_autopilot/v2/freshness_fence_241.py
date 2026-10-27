"""Hard publication fence for current-day, post-start source material.

The source's own timestamp is required. Discovery/processing time cannot make an
old Telegram/RSS post new. The operator's local calendar day is authoritative.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def _aware(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            parsed = parsedate_to_datetime(raw)
        except (ValueError, TypeError, IndexError, OverflowError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def source_freshness_rejection(
    source_published_at: str,
    runtime_started_at: str,
    *,
    now: datetime | None = None,
) -> str:
    """Return a durable rejection code or empty string when source is eligible.

    Use a timezone-aware 'now' only in tests; the live Windows operator's local
    timezone determines the publishing calendar day. A missing or uncertain source
    date fails closed. Runtime start is an absolute timestamp, not discovery time.
    """
    current = now if now is not None else datetime.now().astimezone()
    if current.tzinfo is None:
        return "CLOCK_UNVERIFIED"
    source = _aware(source_published_at)
    started = _aware(runtime_started_at)
    if started is None:
        return "RUNTIME_START_UNVERIFIED"
    if source is None:
        return "SOURCE_DATE_UNVERIFIED"
    if source > current.astimezone(timezone.utc) + timedelta(minutes=2):
        return "SOURCE_DATE_IN_FUTURE"
    if source.astimezone(current.tzinfo).date() != current.date():
        return "SOURCE_NOT_CURRENT_DAY"
    if source < started:
        return "SOURCE_PREDATES_RUNTIME_START"
    return ""
