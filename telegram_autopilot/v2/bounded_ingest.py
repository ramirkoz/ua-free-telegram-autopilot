from __future__ import annotations

import json
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Callable

from ..database import content_hash
from ..models import CollectedArticle, Source
from . import ingest as base
from .loghub import event
from .strict_ingest import StrictIngestService, collect_strict


class BoundedStrictIngestService(StrictIngestService):
    """Keep one slow source from holding the whole monitoring channel hostage.

    Individual collector calls already have transport/enrichment deadlines, but a
    multi-source channel used to wait for every future because the executor context
    manager joins all workers on exit. RC52 gives the channel cycle an aggregate
    budget. Finished sources are committed normally; late sources are put through
    the existing health/cooldown path and their eventual result is discarded.
    """

    channel_source_budget_seconds = 70.0

    def collect_channel(self, channel_id: int, heartbeat: Callable[[], None] | None = None) -> dict[str, int]:
        added = seen = errors = skipped = timed_out = 0

        def beat() -> None:
            if heartbeat is not None:
                try:
                    heartbeat()
                except Exception:
                    pass

        sources: list[Source] = []
        for row in self.store.sources_for_channel(channel_id, enabled_only=True):
            beat()
            source = Source(
                id=int(row["id"]), channel_id=int(row["channel_id"]), kind=str(row["kind"]),
                name=str(row["name"]), url=str(row["url"]), enabled=bool(row["enabled"]),
                initialized=bool(row["initialized"]), last_checked_at=str(row["last_checked_at"] or "") or None,
                last_error=str(row["last_error"] or "") or None, priority=int(row["priority"] or 100),
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
            }

        def fetch_one(source: Source) -> tuple[list[CollectedArticle], int]:
            started = time.monotonic()
            with base._GLOBAL_SOURCE_FETCH_LIMIT:
                items = collect_strict(source)
            return items, int(max(0.0, time.monotonic() - started) * 1000)

        def commit_success(source: Source, items: list[CollectedArticle], duration_ms: int) -> None:
            nonlocal added, seen
            seen += len(items)
            source_added = 0
            for item in items:
                media_json = json.dumps(list(item.media_urls or []), ensure_ascii=False, separators=(",", ":"))
                before = self._existing(channel_id, source.id, item.external_id, item.url)
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
            self.store.record_source_success(source.id, duration_ms)
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

        max_workers = max(1, min(3, len(sources)))
        pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"ingest-{channel_id}")
        future_map: dict[Future[tuple[list[CollectedArticle], int]], tuple[Source, float]] = {
            pool.submit(fetch_one, source): (source, time.monotonic()) for source in sources
        }
        pending: set[Future[tuple[list[CollectedArticle], int]]] = set(future_map)
        deadline = time.monotonic() + max(5.0, float(self.channel_source_budget_seconds))

        try:
            while pending:
                beat()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                done, still_pending = wait(
                    pending,
                    timeout=min(1.0, remaining),
                    return_when=FIRST_COMPLETED,
                )
                pending = set(still_pending)
                if not done:
                    continue
                for future in done:
                    source, submitted_at = future_map[future]
                    try:
                        items, duration_ms = future.result()
                        commit_success(source, items, duration_ms)
                    except Exception as exc:
                        duration_ms = int(max(0.0, time.monotonic() - submitted_at) * 1000)
                        commit_failure(source, str(exc), duration_ms)
                    finally:
                        beat()

            for future in pending:
                source, submitted_at = future_map[future]
                future.cancel()
                duration_ms = int(max(0.0, time.monotonic() - submitted_at) * 1000)
                detail = (
                    f"Source collection exceeded the {int(self.channel_source_budget_seconds)} s "
                    "channel budget; result was isolated and discarded."
                )
                commit_failure(source, detail, duration_ms, timeout=True)
        finally:
            # Do not join still-running network/enrichment workers here. Their collector
            # calls are independently bounded and cannot mutate the V2 store; only this
            # coordinator commits results. Joining them would recreate the old stall.
            pool.shutdown(wait=False, cancel_futures=True)
            beat()

        return {
            "seen": seen, "added": added, "errors": errors,
            "skipped_cooldown": skipped, "timed_out_sources": timed_out,
        }


__all__ = ["BoundedStrictIngestService"]
