"""2.3.28: safe same-day prepared READY continuity across short restarts.

Publication already passes the durable Telegram delivery preflight before
this check. These constraints only remove the false runtime-start veto for an
existing, unsent READY article; they never permit old discovery replay.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .freshness_fence_241 import _aware


def safe_same_day_ready_228(
    source_published_at: str, discovered_at: str, ready_at: str,
    runtime_started_at: str, *, max_age_hours: int = 24,
    now: datetime | None = None,
) -> bool:
    current = now if now is not None else datetime.now().astimezone()
    if current.tzinfo is None:
        return False
    dates = [_aware(value) for value in (
        source_published_at, discovered_at, ready_at, runtime_started_at
    )]
    if any(value is None for value in dates):
        return False
    source, discovered, ready, started = dates
    assert source and discovered and ready and started
    current_utc = current.astimezone(timezone.utc)
    if source.astimezone(current.tzinfo).date() != current.date():
        return False
    if source > current_utc + timedelta(minutes=2):
        return False
    if current_utc - source > timedelta(hours=max(1, min(24, int(max_age_hours)))):
        return False
    # Same original article was discovered, fully prepared and READY before
    # this runtime. The restart is recent; neither older-day backlog nor
    # post-start discovery may inherit the exception.
    return (
        source <= discovered <= ready <= started <= current_utc + timedelta(minutes=2)
        and started - ready <= timedelta(hours=2)
    )



def safe_same_day_queued_2330(
    source_published_at: str, discovered_at: str, runtime_started_at: str,
    source_last_successful_check_at: str, *,
    now: datetime | None = None, max_age_hours: int = 24,
) -> bool:
    """Narrow continuity for *unreviewed* editorial QUEUED rows on short restart.

    Not for preboot READY (handled by safe_same_day_ready_228), archive rows,
    duplicate/delivery-unknown items or old-day stockpiles. Caller MUST verify
    decision=PENDING, no publication metadata and NO delivery journal entry
    before invoking; the downstream Telegram receipt gate also remains active.
    """
    current = now if now is not None else datetime.now().astimezone()
    if current.tzinfo is None:
        return False
    values = [_aware(s) for s in (
        source_published_at, discovered_at, runtime_started_at,
        source_last_successful_check_at
    )]
    if any(v is None for v in values):
        return False
    source, discovered, started, checkpoint = values
    assert source and discovered and started and checkpoint
    utcnow = current.astimezone(timezone.utc)
    if source.astimezone(current.tzinfo).date() != current.date():
        return False
    if source > utcnow + timedelta(minutes=2):
        return False
    if utcnow - source > timedelta(hours=max(1, min(24, int(max_age_hours)))):
        return False
    return (
        source <= discovered <= checkpoint < started <= utcnow + timedelta(minutes=2)
        and started - discovered <= timedelta(hours=2)
        and started - checkpoint <= timedelta(hours=2)
    )
