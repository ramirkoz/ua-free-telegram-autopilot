from __future__ import annotations

import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Callable

from ..database import content_hash
from ..models import CollectedArticle, Source
from .domain import BlockedBy, ChannelMode, Decision, Stage
from .ingest import IngestService, _GLOBAL_SOURCE_FETCH_LIMIT, collect
from .loghub import event
from .media_pipeline import build_media_bundle, media_required
from .runtime import RuntimeEngine


class _CollectionCancelled(RuntimeError):
    pass


class ProductionIngestService(IngestService):
    """Production collection with bounded scheduling and cooperative shutdown.

    Older builds submitted every source in a channel to ThreadPoolExecutor at once.
    A stop/update request then had to wait for the entire queued crawl, so a collector
    could remain alive for many minutes and trip UPDATE_QUIESCE_TIMEOUT. RC31 keeps at
    most three source futures outstanding and stops scheduling immediately when the
    runtime stop event is set. Already-running public HTTP fetches are allowed to finish
    inside their normal bounded network timeouts; no source/database result is committed
    after cancellation.
    """

    def __init__(self, store, *, cancel_requested: Callable[[], bool]):
        super().__init__(store)
        self._cancel_requested = cancel_requested

    def _cancelled(self) -> bool:
        try:
            return bool(self._cancel_requested())
        except Exception:
            return False

    def collect_channel(self, channel_id: int, heartbeat: Callable[[], None] | None = None) -> dict[str, int]:
        added=seen=errors=skipped=0

        def beat() -> None:
            if heartbeat is not None:
                try: heartbeat()
                except Exception: pass

        sources: list[Source] = []
        for row in self.store.sources_for_channel(channel_id,enabled_only=True):
            if self._cancelled():
                return {"seen":seen,"added":added,"errors":errors,"skipped_cooldown":skipped,"cancelled":1}
            beat()
            source=Source(id=int(row["id"]),channel_id=int(row["channel_id"]),kind=str(row["kind"]),name=str(row["name"]),url=str(row["url"]),enabled=bool(row["enabled"]),initialized=bool(row["initialized"]),last_checked_at=str(row["last_checked_at"] or "") or None,last_error=str(row["last_error"] or "") or None,priority=int(row["priority"] or 100))
            cooling,cooldown_until=self.store.source_cooldown_active(source.id)
            if cooling:
                skipped+=1
                event("ingest","source cooldown skip",channel_id=channel_id,source_id=source.id,source=source.name,cooldown_until=cooldown_until)
                continue
            sources.append(source)

        def fetch_one(source: Source) -> tuple[list[CollectedArticle], int]:
            started=time.monotonic()
            acquired=False
            try:
                while not self._cancelled():
                    acquired=_GLOBAL_SOURCE_FETCH_LIMIT.acquire(timeout=0.25)
                    if acquired:
                        break
                if not acquired or self._cancelled():
                    raise _CollectionCancelled("runtime stop requested")
                items=collect(source)
                if self._cancelled():
                    raise _CollectionCancelled("runtime stop requested")
                return items,int(max(0.0,time.monotonic()-started)*1000)
            finally:
                if acquired:
                    _GLOBAL_SOURCE_FETCH_LIMIT.release()

        def commit_result(source: Source, submitted_at: float, future) -> None:
            nonlocal added,seen,errors
            if self._cancelled():
                return
            try:
                items,duration_ms=future.result(); seen+=len(items)
                source_added=0
                # SQLite writes remain serialized in this collector thread. Only
                # network-bound source fetches run in executor workers.
                for item in items:
                    if self._cancelled():
                        return
                    media_json=json.dumps(list(item.media_urls or []),ensure_ascii=False,separators=(",",":"))
                    before=self._existing(channel_id,source.id,item.external_id,item.url)
                    self.store.insert_collected(channel_id=channel_id,source_id=source.id,external_id=item.external_id,title=item.title,source_url=item.url,raw_text=item.raw_text,content_hash=content_hash(item.title,item.raw_text),source_published_at=str(item.published_at or ""),media_json=media_json,article_layout_json=str(item.article_layout_json or "{}"))
                    if not before:
                        added+=1; source_added+=1
                    beat()
                if self._cancelled():
                    return
                self.store.record_source_success(source.id,duration_ms)
                with self.store.connect() as con:
                    con.execute("UPDATE sources SET initialized=1,last_checked_at=?,last_error='' WHERE id=?",(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),source.id))
                event("ingest","source collected",channel_id=channel_id,source_id=source.id,source=source.name,items=len(items),added=source_added,duration_ms=duration_ms)
            except _CollectionCancelled:
                return
            except Exception as exc:
                if self._cancelled():
                    return
                errors+=1
                duration_ms=int(max(0.0,time.monotonic()-submitted_at)*1000)
                failures,cooldown=self.store.record_source_failure(source.id,duration_ms,str(exc))
                with self.store.connect() as con:
                    con.execute("UPDATE sources SET last_checked_at=?,last_error=? WHERE id=?",(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),str(exc)[:1200],source.id))
                event("ingest","source collection failed",level=40,channel_id=channel_id,source_id=source.id,source=source.name,detail=str(exc)[:600],duration_ms=duration_ms,consecutive_failures=failures,cooldown_until=cooldown)
            finally:
                beat()

        max_workers=max(1,min(3,len(sources)))
        if not sources:
            return {"seen":seen,"added":added,"errors":errors,"skipped_cooldown":skipped,"cancelled":int(self._cancelled())}

        pool=ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix=f"ingest-{channel_id}")
        source_iter=iter(sources)
        active: dict[object,tuple[Source,float]]={}

        def fill() -> None:
            while len(active)<max_workers and not self._cancelled():
                try:
                    source=next(source_iter)
                except StopIteration:
                    break
                active[pool.submit(fetch_one,source)]=(source,time.monotonic())

        try:
            fill()
            while active:
                if self._cancelled():
                    for future in list(active):
                        future.cancel()
                done,_=wait(tuple(active),timeout=0.25,return_when=FIRST_COMPLETED)
                if not done:
                    beat()
                    continue
                for future in done:
                    source,submitted_at=active.pop(future)
                    commit_result(source,submitted_at,future)
                fill()
        finally:
            cancelled=self._cancelled()
            if cancelled:
                for future in list(active):
                    future.cancel()
            # Only the <=3 already-running public fetches may remain here. They use
            # bounded HTTP/deadline logic; unlike RC29 there is no channel-sized
            # executor backlog left to drain before the collector thread can exit.
            pool.shutdown(wait=True,cancel_futures=True)

        if self._cancelled():
            event("ingest","collection cooperatively cancelled",channel_id=channel_id,seen=seen,added=added)
        return {"seen":seen,"added":added,"errors":errors,"skipped_cooldown":skipped,"cancelled":int(self._cancelled())}


class ProductionRuntimeEngine(RuntimeEngine):
    """Production runtime hardening for queues, media recovery and clean updates."""

    def __init__(self, store):
        super().__init__(store)
        self.ingest=ProductionIngestService(store,cancel_requested=lambda: self.stop_event.is_set())
        self._media_sweeper_stop = threading.Event()
        self._media_sweeper_thread: threading.Thread | None = None

    def start(self) -> None:
        super().start()
        if not self._media_sweeper_thread or not self._media_sweeper_thread.is_alive():
            self._media_sweeper_stop.clear()
            self._media_sweeper_thread = threading.Thread(
                target=self._media_sweeper_loop,
                name="V2-Media-Sweeper",
                daemon=True,
            )
            self._media_sweeper_thread.start()

    def stop(self, timeout: float = 8.0) -> None:
        self._media_sweeper_stop.set()
        super().stop(timeout=timeout)
        thread = self._media_sweeper_thread
        if thread and thread.is_alive():
            thread.join(min(2.0, max(0.2, float(timeout))))

    def _media_sweeper_loop(self) -> None:
        while not self._media_sweeper_stop.wait(15.0):
            try:
                self._resolve_confirmed_media_misses()
            except Exception as exc:
                event("media", "required-media sweeper failed", level=30, detail=str(exc)[:1000])

    def _resolve_confirmed_media_misses(self) -> int:
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT j.id job_id,j.article_id,a.channel_id,a.last_error_code
                   FROM jobs j JOIN articles a ON a.id=j.article_id
                   WHERE j.state='WAITING' AND a.decision='PENDING' AND a.blocked_by='MEDIA'
                     AND a.last_error_code IN ('MEDIA_REQUIRED','TELEGRAM_MEDIA_REFRESH_REQUIRED')
                   ORDER BY j.updated_at ASC LIMIT 250"""
            ).fetchall()

        resolved = 0
        for row in rows:
            channel = self.store.get_channel(int(row["channel_id"]))
            if channel is None or channel.mode != ChannelMode.MONITORING or not media_required(channel):
                continue
            article = self.store.get_article(int(row["article_id"]))
            if article is None or build_media_bundle(article).count:
                continue
            reason = "Моніторинговий матеріал пропущено: після strict ownership/media filter немає валідного медіа точного джерельного поста."
            self.store.update_article(
                int(row["article_id"]),
                stage=str(Stage.ARCHIVED),
                decision=str(Decision.REJECT),
                blocked_by=str(BlockedBy.NONE),
                reject_reason=reason,
                last_error_code="MEDIA_REQUIRED_SKIPPED",
                last_error_detail=reason,
                next_retry_at="",
            )
            self.store.finish_job(int(row["job_id"]))
            resolved += 1
        if resolved:
            event("media", "resolved permanent required-media backlog", count=resolved)
        return resolved
