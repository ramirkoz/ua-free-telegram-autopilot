"""Read-only publication-capacity estimate for safer pending-job prioritization.

This module never changes an operator's publishing interval, opens channels,
deletes jobs, or bypasses editorial/media gates.
"""
from __future__ import annotations

from math import ceil


def _minutes(value: str) -> int | None:
    try:
        hours, minutes = str(value).split(":", 1)
        hh, mm = int(hours), int(minutes)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh * 60 + mm
    except (TypeError, ValueError):
        pass
    return None


def capacity_window(
    *,
    pending_jobs: int,
    min_interval_minutes: int,
    publish_24h: bool,
    publish_start: str,
    publish_end: str,
    max_age_hours: int,
) -> dict[str, int | bool | str]:
    """Conservative capacity projection, *not* a delivery schedule or quota.

    The overcapacity rule is intentionally delayed until the backlog exceeds
    twice the optimistic number of publish slots within the source TTL.
    When overloaded, fresh news is selected before stale jobs close to expiry.
    Pending rows remain untouched and retain the normal TTL and safety checks.
    """
    gap = max(0, int(min_interval_minutes or 0))
    max_age = max(1, int(max_age_hours or 24))
    if bool(publish_24h):
        window_minutes = 1440
    else:
        begin, end = _minutes(publish_start), _minutes(publish_end)
        if begin is None or end is None:
            window_minutes = 1440  # Uncertain schedule: avoid false overload.
        elif end > begin:
            window_minutes = end - begin
        elif end < begin:
            window_minutes = 1440 - begin + end
        else:
            window_minutes = 1440

    # Large TTLs can span multiple available daily windows. Rounding upward is
    # deliberate: switch only when backlog overwhelms a generous upper bound.
    windows = max(1, ceil(max_age / 24))
    slots = max(1, window_minutes // max(1, gap)) * windows
    threshold = max(12, 2 * slots)
    overloaded = gap >= 10 and int(pending_jobs) > threshold
    return {
        "publish_slots_before_ttl_estimate": int(slots),
        "overload_threshold": int(threshold),
        "pending_jobs": max(0, int(pending_jobs)),
        "overloaded": overloaded,
        "pending_selection": "FRESHNESS_FIRST" if overloaded else "RESCUE_NEAR_TTL",
        "preserves_operator_interval": True,
        # Diagnostic only: pending items are *selection jobs*, NOT 1:1
        # publishable posts. Never change cadence or silently delete articles.
        "selection_jobs_per_possible_post_slot": round(
            max(0, int(pending_jobs)) / max(1, slots), 2,
        ),
        "selection_pressure": (
            "HIGH" if overloaded else (
                "ELEVATED" if int(pending_jobs) > slots else "NORMAL"
            )
        ),
        "jobs_are_not_posts": True,
        "automatic_drop_or_interval_change": False,
    }
