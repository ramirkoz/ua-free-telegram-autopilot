"""v2.2.40: commercial source scheduling based on real publication yield.

Prioritization reorders the *existing* source queue; it never disables sources,
changes their configured priorities, bypasses cooldowns, or changes editorial QA.
The production funnel is read-only and cannot replay an old article.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .commercial_diversity_257 import source_concentration_penalty_257


def _value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def prioritize_commercial_sources(
    sources: Iterable[Any], health_rows: Iterable[Any],
    yield_rows: Iterable[Any] | None = None,
    *, published_share_7d: dict[int, float] | None = None,
    published_total_7d: int = 0,
    published_sources_7d: int = 0,
) -> list[Any]:
    """2.2.40: schedule the same source set by *published* yield, not raw intake.

    Last-added counts alone can reward sources whose feeds produce only short
    summaries or policy-rejected articles (operator LIVE: 23/23 rejected on Muse
    by Clio while Creative Bloq published 4/6). The source's existing priority
    remains the base, and no source is disabled, bypassed or skipped.
    """
    health = {int(_value(row, "source_id", 0) or 0): row for row in health_rows}
    cohort = {int(_value(row, "source_id", 0) or 0): row for row in (yield_rows or ())}

    def score(source: Any) -> tuple[int, int, int]:
        h = health.get(int(source.id))
        y = cohort.get(int(source.id))
        baseline = int(getattr(source, "priority", 100) or 100)
        last_added = max(0, int(_value(h, "last_added", 0) or 0))
        duration_ms = max(0, int(_value(h, "last_duration_ms", 0) or 0))
        outcome = str(_value(h, "last_outcome", "") or "").upper()

        discovered = max(0, int(_value(y, "collected", 0) or 0))
        published = max(0, min(discovered, int(_value(y, "published", 0) or 0)))
        short_rejected = max(0, min(discovered, int(_value(y, "short_source_rejected", 0) or 0)))
        if discovered >= 5:
            # Six discovered articles with four real publications should beat
            # twenty-three discovered with zero published. Max change +/-12;
            # it cannot override a wildly different operator priority.
            benefit = min(12, published * 4)
            low_yield_penalty = (
                10 if published == 0 and discovered >= 10 else
                5 if published == 0 and discovered >= 5 else 0
            )
            # If a whole feed is a short excerpt, fetch it *later*, not never.
            short_penalty = 3 if short_rejected >= 5 else 0
        elif published:
            benefit = min(8, published * 4)
            low_yield_penalty = short_penalty = 0
        elif y is None:
            # No reliable cohort yet: retain a very small fresh-intake hint.
            benefit = min(4, last_added * 2)
            low_yield_penalty = short_penalty = 0
        else:
            benefit = low_yield_penalty = short_penalty = 0
        slow_penalty = min(24, duration_ms // 5000) if last_added == 0 else 0
        failure_penalty = 12 if outcome in {"TIMEOUT", "NETWORK", "ERROR", "HTTP_403", "HTTP_429"} else 0
        diversity_penalty = source_concentration_penalty_257(
            int(source.id), published_share_7d or {},
            total_posts=published_total_7d, source_count=published_sources_7d,
        )
        return (
            baseline - benefit + low_yield_penalty + short_penalty + slow_penalty + failure_penalty + diversity_penalty,
            baseline, int(source.id),
        )

    return sorted(sources, key=score)


def commercial_source_yield_rows_24h(store: Any, channel_id: int) -> list[Any]:
    """One read-only indexed-cohort query, used only for commercial ordering."""
    cut = (datetime.now(timezone.utc) - timedelta(hours=24)).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        return con.execute(
            """SELECT source_id, COUNT(*) AS collected,
                      SUM(CASE WHEN published_at<>'' THEN 1 ELSE 0 END) AS published,
                      SUM(CASE WHEN decision='REJECT'
                                   AND reject_reason LIKE 'EDITORIAL_MIN_TWO_SENTENCES: source%'
                               THEN 1 ELSE 0 END) AS short_source_rejected
               FROM articles
               WHERE channel_id=? AND discovered_at>=?
               GROUP BY source_id""",
            (int(channel_id), cut),
        ).fetchall()


def commercial_source_funnel_24h(store: Any, channel_id: int, *, limit: int = 48) -> dict[str, Any]:
    """Report collected→editorial→published by original source without mutations.

    A published article is counted via published_at, not a transient stage.
    Only articles discovered in the 24h window count toward this *cohort*,
    so day counts can differ from publications of older queued articles.
    """
    cut = (datetime.now(timezone.utc) - timedelta(hours=24)).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        sources = con.execute(
            """SELECT s.id,s.name,s.url,s.enabled,s.priority,
                      COALESCE(h.last_duration_ms,0) AS last_duration_ms,
                      COALESCE(h.last_outcome,'') AS last_outcome,
                      COALESCE(h.last_added,0) AS last_added,
                      COALESCE(h.cooldown_until,'') AS cooldown_until
                 FROM sources s LEFT JOIN source_health h ON h.source_id=s.id
                 WHERE s.channel_id=? ORDER BY s.priority,s.id LIMIT ?""",
            (int(channel_id), max(1, min(100, int(limit)))),
        ).fetchall()
        counts = con.execute(
            """SELECT source_id,
                      COUNT(*) AS collected,
                      SUM(CASE WHEN decision='REJECT' THEN 1 ELSE 0 END) AS rejected,
                      SUM(CASE WHEN decision='REJECT'
                                   AND reject_reason LIKE 'EDITORIAL_MIN_TWO_SENTENCES: source%'
                               THEN 1 ELSE 0 END) AS short_source_rejected,
                      SUM(CASE WHEN decision='DUPLICATE' THEN 1 ELSE 0 END) AS duplicates,
                      SUM(CASE WHEN published_at<>'' THEN 1 ELSE 0 END) AS published,
                      SUM(CASE WHEN stage='READY' AND published_at='' THEN 1 ELSE 0 END) AS ready,
                      SUM(CASE WHEN blocked_by='MEDIA' AND published_at='' THEN 1 ELSE 0 END) AS media_blocked
               FROM articles
               WHERE channel_id=? AND discovered_at>=?
               GROUP BY source_id""",
            (int(channel_id), cut),
        ).fetchall()
    cohorts = {int(row["source_id"]): row for row in counts}
    records: list[dict[str, Any]] = []
    for s in sources:
        id_ = int(s["id"])
        v = cohorts.get(id_)
        records.append({
            "source_id": id_,
            "name": str(s["name"] or "")[:120],
            "enabled": bool(s["enabled"]),
            "priority": int(s["priority"] or 100),
            "collected_24h": int(_value(v, "collected", 0) or 0),
            "rejected_24h": int(_value(v, "rejected", 0) or 0),
            "short_source_rejected_24h": int(_value(v, "short_source_rejected", 0) or 0),
            "duplicates_24h": int(_value(v, "duplicates", 0) or 0),
            "published_24h": int(_value(v, "published", 0) or 0),
            "ready_24h": int(_value(v, "ready", 0) or 0),
            "media_blocked_24h": int(_value(v, "media_blocked", 0) or 0),
            "last_duration_ms": int(s["last_duration_ms"] or 0),
            "last_outcome": str(s["last_outcome"] or ""),
            "last_added": int(s["last_added"] or 0),
            "cooldown_until": str(s["cooldown_until"] or ""),
        })
    return {
        "scope": "commercial_source_cohort_24h_read_only",
        "window_hours": 24,
        "source_count": len(records),
        "sources": records,
        "collected_24h": sum(x["collected_24h"] for x in records),
        "published_24h": sum(x["published_24h"] for x in records),
        "rejected_24h": sum(x["rejected_24h"] for x in records),
        "short_source_rejected_24h": sum(x["short_source_rejected_24h"] for x in records),
        "media_blocked_24h": sum(x["media_blocked_24h"] for x in records),
        "source_cooldowns_not_overridden": True,
        "editorial_thresholds_unchanged": True,
    }
