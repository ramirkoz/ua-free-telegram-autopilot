from __future__ import annotations

import json
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from ..database import content_hash
from ..models import CollectedArticle, Source
from . import ingest as base
from .loghub import event
from .strict_ingest import StrictIngestService, collect_strict
from .commercial_yield_237 import prioritize_commercial_sources, commercial_source_yield_rows_24h
from .commercial_fetch_effort_247 import commercial_page_fetch_limits
from .freshness_fence_241 import source_freshness_rejection


class BoundedStrictIngestService(StrictIngestService):
    """Keep one slow source from holding the whole monitoring channel hostage.

    RC52/RC53 used one aggregate 70-second channel clock after submitting every
    source behind only three workers. Queued sources were therefore marked failed
    before they even started. RC54 uses a rolling scheduler and a per-source clock.
    Finished sources are committed normally; only the source that actually exceeds
    its own deadline is cooled down and its late result is discarded.
    """

    source_timeout_seconds = 70.0
    active_source_slots = 3
    worker_headroom = 6

    def _repair_v2247_commercial_keyword_cooldowns(self, channel_id: int) -> int:
        """Undo only persisted false cooldowns caused by the 2.2.47 adapter TypeError.

        Keep real HTTP403/429/network failures and all success/failure history.
        The exact error match and channel profile make repeated calls idempotent.
        """
        with self.store.connect() as con:
            row = con.execute(
                "SELECT editorial_runtime_profile FROM channels WHERE id=?",
                (int(channel_id),),
            ).fetchone()
            if row is None or str(row["editorial_runtime_profile"]) != "commercial_editorial":
                return 0
            stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            cur = con.execute(
                """UPDATE source_health
                   SET consecutive_failures=0, cooldown_until='',
                       last_outcome='RECOVERED_248', last_error='', updated_at=?
                   WHERE source_id IN (
                       SELECT id FROM sources WHERE channel_id=? AND enabled=1
                   )
                     AND last_outcome='ERROR'
                     AND last_error=?""",
                (stamp, int(channel_id),
                 "_collect_current() got an unexpected keyword argument 'rss_enrich_eligible'"),
            )
            repaired = int(cur.rowcount or 0)
        if repaired:
            event(
                "ingest", "recovered exact 2.2.47 commercial adapter cooldowns",
                level=30, channel_id=channel_id, sources=repaired,
                untouched_real_network_errors=True,
            )
        return repaired

    def _repair_legacy_budget_cooldowns(self, channel_id: int) -> int:
        """Clear only cooldowns created by the broken RC52/RC53 channel-wide timer."""
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.store.connect() as con:
            cur = con.execute(
                """UPDATE source_health
                   SET consecutive_failures=0,cooldown_until='',last_outcome='RECOVERED',last_error='',updated_at=?
                   WHERE source_id IN (SELECT id FROM sources WHERE channel_id=?)
                     AND last_error LIKE 'Source collection exceeded the % channel budget; result was isolated and discarded.%'""",
                (stamp, int(channel_id)),
            )
            changed = int(cur.rowcount or 0)
        if changed:
            event("ingest", "repaired false RC52/RC53 source cooldowns", level=30, channel_id=channel_id, sources=changed)
        return changed

    def collect_channel(self, channel_id: int, heartbeat: Callable[[], None] | None = None) -> dict[str, int]:
        added = seen = errors = skipped = timed_out = known_external = known_url = sources_with_new = stale_filtered = 0
        cfg = self.store.get_channel(channel_id)
        with self.store.connect() as con:
            runtime_row = con.execute(
                "SELECT value FROM meta WHERE key='runtime_source_freshness_started_at'"
            ).fetchone()
        runtime_started_at = str(runtime_row[0] or "") if runtime_row else ""

        def beat() -> None:
            if heartbeat is not None:
                try:
                    heartbeat()
                except Exception:
                    pass

        self._repair_v2247_commercial_keyword_cooldowns(channel_id)
        self._repair_legacy_budget_cooldowns(channel_id)

        # A source-owned override can request direct HTML even when this
        # channel normally prefers public feeds. Used for broken/stale feeds;
        # no hardcoded commercial channel or publisher names.
        page_first_source_ids: set[int] = set()
        sources: list[Source] = []
        for row in self.store.sources_for_channel(channel_id, enabled_only=True):
            beat()
            try:
                source_settings = json.loads(str(row["legacy_config_json"] or "{}"))
            except (ValueError, TypeError):
                source_settings = {}
            if isinstance(source_settings, dict):
                override = source_settings.get("commercial_sources_229")
                if isinstance(override, dict) and override.get("force_page_first") is True:
                    page_first_source_ids.add(int(row["id"]))
            source = Source(
                id=int(row["id"]), channel_id=int(row["channel_id"]), kind=str(row["kind"]),
                name=str(row["name"]), url=str(row["url"]), enabled=bool(row["enabled"]),
                initialized=bool(row["initialized"]), last_checked_at=str(row["last_checked_at"] or "") or None,
                last_error=str(row["last_error"] or "") or None, priority=int(row["priority"] or 100),
                reader_fallback_enabled=self.store.source_reader_fallback_enabled(int(row["id"])),
            )
            cooling, cooldown_until = self.store.source_cooldown_active(source.id)
            if cooling:
                skipped += 1
                event(
                    "ingest", "source cooldown skip", channel_id=channel_id, source_id=source.id,
                    source=source.name, cooldown_until=cooldown_until,
                )
                continue
            sources.append(source)

        if not sources:
            return {
                "seen": seen, "added": added, "errors": errors,
                "skipped_cooldown": skipped, "timed_out_sources": timed_out,
                "known_external_id": known_external, "known_canonical_url": known_url, "sources_with_new": sources_with_new,
            }

        # 2.2.37: commercial source queue runs high-yield, lower-latency feeds
        # sooner. Every eligible source is still collected once. Operator
        # source selection, cooldowns, editorial policy and quotas are unchanged.
        commercial_profile = str(getattr(cfg, "editorial_runtime_profile", "")) == "commercial_editorial"
        page_limits_by_source: dict[int, tuple[int, int]] = {}
        if commercial_profile:
            with self.store.connect() as con:
                health_rows = con.execute(
                    """SELECT source_id,last_added,last_duration_ms,last_outcome
                       FROM source_health
                       WHERE source_id IN (SELECT id FROM sources WHERE channel_id=?)""",
                    (int(channel_id),),
                ).fetchall()
            original_ids = [source.id for source in sources]
            # v2.2.40: recent *published* results, not just raw additions,
            # determine the mild fast-first weight. Noncommercial untouched.
            yield_rows = commercial_source_yield_rows_24h(self.store, channel_id)
            sources = prioritize_commercial_sources(sources, health_rows, yield_rows)
            page_limits_by_source = commercial_page_fetch_limits(
                sources, health_rows, yield_rows,
                page_fetch_limit=int(getattr(cfg, "page_fetch_limit", 8)),
                page_candidate_scan_limit=int(getattr(cfg, "page_candidate_scan_limit", 24)),
            )
            if page_limits_by_source:
                event(
                    "ingest", "commercial slow homepage fetch reduced",
                    channel_id=channel_id, sources=[
                        {"source_id": source.id, "name": source.name, "scan": page_limits_by_source[source.id][0],
                         "fetch": page_limits_by_source[source.id][1]}
                        for source in sources if source.id in page_limits_by_source
                    ], enabled_roster_unchanged=True, editorial_policy_unchanged=True,
                )
            if original_ids != [source.id for source in sources]:
                event(
                    "ingest", "commercial fast-first collection order",
                    channel_id=channel_id, source_count=len(sources),
                    first_sources=[source.name for source in sources[:4]],
                    unmodified_source_set=True, cooldowns_preserved=True,
                    fast_first_metric="published_source_cohort_24h",
                )

        def fetch_one(source: Source) -> tuple[list[CollectedArticle], int]:
            started = time.monotonic()
            page_scan, page_fetch = page_limits_by_source.get(
                source.id,
                (int(getattr(cfg, "page_candidate_scan_limit", 24)),
                 int(getattr(cfg, "page_fetch_limit", 8))),
            )
            # Editorial sources have the original fetch path. For commercial
            # feeds, only enrich stories actually eligible AFTER runtime start;
            # source items still reach the ordinary date/dedupe pre-AI gate.
            freshness = (
                (lambda item: not source_freshness_rejection(
                    str(item.published_at or ""), runtime_started_at))
                if commercial_profile and runtime_started_at else None
            )
            with base._GLOBAL_SOURCE_FETCH_LIMIT:
                kwargs = dict(
                    page_prefer_feed=bool(getattr(cfg, "page_prefer_feed", False)) and source.id not in page_first_source_ids,
                    page_candidate_scan_limit=page_scan, page_fetch_limit=page_fetch,
                )
                if freshness is not None and source.kind in {"rss", "page"}:
                    kwargs["rss_enrich_eligible"] = freshness
                items = collect_strict(source, **kwargs)
            return items, int(max(0.0, time.monotonic() - started) * 1000)

        def commit_success(source: Source, items: list[CollectedArticle], duration_ms: int) -> None:
            nonlocal added, seen, known_external, known_url, sources_with_new, stale_filtered
            seen += len(items)
            source_added = 0
            for item in items:
                stale_reason = source_freshness_rejection(
                    str(item.published_at or ""), runtime_started_at
                ) if runtime_started_at else ""
                if stale_reason:
                    stale_filtered += 1
                    continue
                if '"source_reader"' in str(item.article_layout_json or ""):
                    event(
                        "reader", "optional source reader used",
                        channel_id=channel_id, source_id=source.id,
                        source=source.name, article_url=item.url, reader="jina",
                    )
                media_json = json.dumps(list(item.media_urls or []), ensure_ascii=False, separators=(",", ":"))
                reason = self._existing_reason(channel_id, source.id, item.external_id, item.url)
                before = bool(reason)
                if reason == "external_id": known_external += 1
                elif reason == "canonical_url": known_url += 1
                self.store.insert_collected(
                    channel_id=channel_id, source_id=source.id, external_id=item.external_id,
                    title=item.title, source_url=item.url, raw_text=item.raw_text,
                    content_hash=content_hash(item.title, item.raw_text),
                    source_published_at=str(item.published_at or ""), media_json=media_json,
                    article_layout_json=str(item.article_layout_json or "{}"),
                )
                if not before:
                    added += 1
                    source_added += 1
                beat()
            if source_added:
                sources_with_new += 1
            self.store.record_source_success(source.id, duration_ms, items=len(items), added=source_added)
            with self.store.connect() as con:
                con.execute(
                    "UPDATE sources SET initialized=1,last_checked_at=?,last_error='' WHERE id=?",
                    (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), source.id),
                )
            event(
                "ingest", "source collected", channel_id=channel_id, source_id=source.id,
                source=source.name, items=len(items), added=source_added, duration_ms=duration_ms,
            )

        def commit_failure(source: Source, detail: str, duration_ms: int, *, timeout: bool = False) -> None:
            nonlocal errors, timed_out
            errors += 1
            if timeout:
                timed_out += 1
            failures, cooldown = self.store.record_source_failure(source.id, duration_ms, detail)
            with self.store.connect() as con:
                con.execute(
                    "UPDATE sources SET last_checked_at=?,last_error=? WHERE id=?",
                    (
                        datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                        detail[:1200], source.id,
                    ),
                )
            event(
                "ingest", "source collection timed out" if timeout else "source collection failed",
                level=30 if timeout else 40, channel_id=channel_id,
                source_id=source.id, source=source.name, detail=detail[:600], duration_ms=duration_ms,
                consecutive_failures=failures, cooldown_until=cooldown,
            )

        # RC54: never submit the whole channel behind three workers and then time out
        # queued futures with one channel-wide clock.  Keep only a small rolling set
        # of actually-started sources.  A timeout applies to that source alone.
        active_limit = max(1, min(int(self.active_source_slots), len(sources)))
        max_workers = max(active_limit, min(int(self.worker_headroom), len(sources)))
        pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"ingest-{channel_id}")
        waiting_sources = deque(sources)
        active: dict[Future[tuple[list[CollectedArticle], int]], tuple[Source, float]] = {}
        abandoned: set[Future[tuple[list[CollectedArticle], int]]] = set()

        def submit_next() -> None:
            while waiting_sources and len(active) < active_limit:
                source = waiting_sources.popleft()
                future = pool.submit(fetch_one, source)
                active[future] = (source, time.monotonic())
                event(
                    "ingest", "source collection started", channel_id=channel_id,
                    source_id=source.id, source=source.name, active=len(active), queued=len(waiting_sources),
                )

        submit_next()
        try:
            while active:
                beat()
                now = time.monotonic()
                progressed = False

                for future in list(active):
                    if not future.done():
                        continue
                    progressed = True
                    source, started_at = active.pop(future)
                    try:
                        items, duration_ms = future.result()
                        commit_success(source, items, duration_ms)
                    except Exception as exc:
                        duration_ms = int(max(0.0, now - started_at) * 1000)
                        commit_failure(source, str(exc), duration_ms)
                    finally:
                        beat()

                # Only running/submitted active sources can time out. Sources still in
                # waiting_sources have no clock and therefore cannot be falsely failed.
                now = time.monotonic()
                for future, (source, started_at) in list(active.items()):
                    if now - started_at < max(5.0, float(self.source_timeout_seconds)):
                        continue
                    progressed = True
                    active.pop(future, None)
                    abandoned.add(future)
                    future.cancel()
                    duration_ms = int(max(0.0, now - started_at) * 1000)
                    detail = (
                        f"Source collection exceeded its {int(self.source_timeout_seconds)} s per-source timeout; "
                        "late result was isolated and discarded."
                    )
                    commit_failure(source, detail, duration_ms, timeout=True)
                    beat()

                submit_next()
                if not progressed:
                    time.sleep(0.20)

            # Futures that timed out may still be unwinding their own network deadline.
            # Their result is intentionally ignored and they never block the next source.
            for future in abandoned:
                future.cancel()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            beat()

        if stale_filtered:
            event("ingest", "source day/start fence skipped old items",
                  channel_id=channel_id, skipped=stale_filtered,
                  runtime_started_at=runtime_started_at)
        return {
            "seen": seen, "added": added, "errors": errors,
            "skipped_cooldown": skipped, "timed_out_sources": timed_out,
            "known_external_id": known_external, "known_canonical_url": known_url, "sources_with_new": sources_with_new,
            "stale_filtered": stale_filtered,
        }


__all__ = ["BoundedStrictIngestService"]
