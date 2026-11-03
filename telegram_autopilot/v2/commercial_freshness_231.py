"""2.3.1 RSS intake evidence: distinguish broken feed, no new issue and age fence.

Read-only classification of articles already fetched by the standard bounded
collector. No new HTTP requests or changes to publishing eligibility.
"""
from __future__ import annotations

from .freshness_fence_241 import _aware, restart_source_rejection
from typing import Any, Callable, Iterable



def diagnose_migrated_feed_231(
    items: Iterable[Any], runtime_started_at: str, checkpoint: str,
    existing_reason: Callable[[Any], str],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    newest = None
    for article in items:
        stamp = str(getattr(article, "published_at", "") or "")
        # RSS pubDate and Atom ISO timestamps are not lexically comparable.
        # Parse both into UTC and do not guess if the source timestamp is bad.
        parsed = _aware(stamp)
        if parsed is not None and (newest is None or parsed > newest):
            newest = parsed
        reason = restart_source_rejection(stamp, runtime_started_at, checkpoint)
        if reason:
            label = reason
        else:
            known = existing_reason(article)
            label = "KNOWN_ARTICLE" if known else "NEW_DATE_ELIGIBLE"
        counts[label] = counts.get(label, 0) + 1
    return {
        "items": sum(counts.values()), "date_buckets": counts,
        "newest_publisher_timestamp": newest.isoformat() if newest is not None else "",
        "diagnostic_only": True, "source_date_fence_preserved": True,
        "new_source_http_requests": 0, "backlog_replay": False,
    }
