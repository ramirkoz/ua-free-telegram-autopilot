"""v2.2.37: fast-first commercial source collection and factual 24h yield audit.

Prioritization reorders the *existing* source queue; it never disables sources,
changes their configured priorities, bypasses cooldowns, or changes editorial QA.
The production funnel is read-only and cannot replay an old article.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


def _value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def prioritize_commercial_sources(
    sources: Iterable[Any], health_rows: Iterable[Any]
) -> list[Any]:
    """Use mild empirical yield/latency weights while preserving every source.

    Never rank a source on a policy-rejected article as an automatic editorial
    approval; the ordering only decides which scheduled HTTP fetch starts first.
    """
    health = {int(_value(row, "source_id", 0) or 0): row for row in health_rows}

    def score(source: Any) -> tuple[int, int, int]:
        h = health.get(int(source.id))
        baseline = int(getattr(source, "priority", 100) or 100)
        last_added = max(0, int(_value(h, "last_added", 0) or 0))
        duration_ms = max(0, int(_value(h, "last_duration_ms", 0) or 0))
        outcome = str(_value(h, "last_outcome", "") or "").upper()
        # Keep the operator priority meaningful. A fast source with actual
        # fresh articles gets at most a 12-point advantage; 30+ second known-
        # only runs yield at most a 24-point penalty. Nothing is skipped.
        bonus = min(12, 4 * last_added)
        slow_penalty = min(24, duration_ms // 5000) if last_added == 0 else 0
        failure_penalty = 12 if outcome in {"TIMEOUT", "NETWORK", "ERROR", "HTTP_403", "HTTP_429"} else 0
        return (baseline - bonus + slow_penalty + failure_penalty,
                baseline, int(source.id))

    return sorted(sources, key=score)


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
        "media_blocked_24h": sum(x["media_blocked_24h"] for x in records),
        "source_cooldowns_not_overridden": True,
        "editorial_thresholds_unchanged": True,
    }
