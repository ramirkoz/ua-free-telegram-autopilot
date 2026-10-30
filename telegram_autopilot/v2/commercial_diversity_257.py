"""v2.2.57: read-only seven-day source-concentration signal for commercial source ordering.

A source's own recent published posts are not a reason to grant it an unlimited
head-start every cycle. Never hard-cap, disable, discard, or force publication.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def commercial_published_share_7d(store: Any, channel_id: int) -> dict[str, Any]:
    """Return confirmed published counts by source without changing operator Data.

    A seven-day window uses published_at, not discovery or pending attempts;
    UNKNOWN Telegram deliveries are not counted as successful via a stage guess.
    The scalar source count is used as an advisory scheduler signal only.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        rows = con.execute(
            """SELECT a.source_id, COUNT(*) AS posts
               FROM articles a
               WHERE a.channel_id=? AND a.published_at>=? AND a.published_at<>''
               GROUP BY a.source_id""",
            (int(channel_id), cutoff),
        ).fetchall()
    counts = {int(row["source_id"]): int(row["posts"]) for row in rows if row["source_id"] is not None}
    total = sum(counts.values())
    return {
        "window_days": 7,
        "scope": "read_only_published_at",
        "total_posts": total,
        "source_count": len(counts),
        "counts": counts,
        "shares": {sid: round(n / total, 5) for sid, n in counts.items()} if total else {},
        "operator_source_state_unchanged": True,
        "editorial_policy_unchanged": True,
    }


def source_concentration_penalty_257(
    source_id: int, shares: dict[int, float], *, total_posts: int, source_count: int
) -> int:
    """Small ordering penalty beyond 30% share once diversity has a sample.

    A *schedule-order* modifier, not a publication cap or editorial reject.
    With a small sample or only one proven source, do not pretend that a
    statistical source-diversity signal is established.
    """
    if total_posts < 12 or source_count < 2:
        return 0
    share = max(0.0, min(1.0, float(shares.get(int(source_id), 0.0) or 0.0)))
    if share <= 0.30:
        return 0
    return min(25, 5 + round((share - 0.30) * 36))
