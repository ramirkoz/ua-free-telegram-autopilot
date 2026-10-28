"""2.2.47 commercial-only source fetch effort, backed by observed LIVE yield.

Retain every enabled source, operator priorities and normal publication rules.
Slow, zero-yield HTML listings get fewer expensive article-page enrichments,
but are still polled every cycle. A successful source immediately returns to
full configured fetch depth. No network bypass for HTTP 403/522.
"""
from __future__ import annotations

from typing import Any, Iterable

def _field(value: Any, name: str, default: Any = None) -> Any:
    try:
        x = value[name]
    except (TypeError, KeyError, IndexError):
        return default
    return default if x is None else x


def commercial_page_fetch_limits(
    sources: Iterable[Any],
    health_rows: Iterable[Any],
    yield_rows: Iterable[Any],
    *,
    page_fetch_limit: int,
    page_candidate_scan_limit: int,
) -> dict[int, tuple[int, int]]:
    """Only reduce low-yield slow PAGE-source work; restore on recent success.

    An RSS or Telegram source is not a homepage, so their bounds are untouched.
    A page with any published result in the last 24h remains fully eligible.
    """
    health = {int(_field(h, "source_id", 0) or 0): h for h in health_rows}
    yield_by_id = {int(_field(y, "source_id", 0) or 0): y for y in yield_rows}
    configured_fetch = max(4, int(page_fetch_limit or 8))
    configured_scan = max(8, int(page_candidate_scan_limit or 24))
    result: dict[int, tuple[int, int]] = {}
    for source in sources:
        if str(getattr(source, "kind", "")).casefold() != "page":
            continue
        sid = int(source.id)
        h = health.get(sid)
        if h is None:
            continue
        # No cohort means no evidence of unproductive collection; never
        # restrict a newly operator-added feed or new creative campaign.
        y = yield_by_id.get(sid)
        if y is None:
            continue
        published = int(_field(y, "published", 0) or 0)
        last_added = int(_field(h, "last_added", 0) or 0)
        last_duration = int(_field(h, "last_duration_ms", 0) or 0)
        if published or last_added or last_duration < 35000:
            continue
        # Still fetch 4 full pages, rather than disabling or treating
        # "no newly published" as editorial rejection.
        limits = (min(configured_scan, 12), min(configured_fetch, 4))
        if limits != (configured_scan, configured_fetch):
            result[sid] = limits
    return result
