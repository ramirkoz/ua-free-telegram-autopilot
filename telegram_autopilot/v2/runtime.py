from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .ai_gateway import AIGateway, GatewayExhausted
from .dedupe import DedupeEngine
from .domain import BlockedBy, Decision, Stage
from .editorial import EditorialEngine
from .ingest import IngestService
from .loghub import event
from .publisher import Publisher
from .storage import V2Store


@dataclass(slots=True)
class ChannelRuntimeState:
    channel_id: int
    last_collect_monotonic: float = 0.0
    last_publish_monotonic: float = 0.0
    processed: int = 0
    published: int = 0
    errors: int = 0
    heartbeat_at: str = ""


class RuntimeEngine:
    """Clean V2 scheduler: one isolated preparation loop per channel.

    A slow/broken source or AI request in one channel cannot starve another channel.
    Durable leases/jobs survive process restarts; the SQLite job queue is the truth.
    """

    def __init__(self, store: V2Store):
        self.store = store
        self.gateway = AIGateway(store)
        self.ingest = IngestService(store)
        self.dedupe = DedupeEngine(store)
        self.editorial = EditorialEngine(store, self.gateway)
        self.publisher = Publisher(store)
        self.stop_event = threading.Event()
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.RLock()
        self.states: dict[int, ChannelRuntimeState] = {}

    def start(self) -> None:
        self.store.recover_stale_leases()
        self.stop_event.clear()
        for row in self.store.list_channels(enabled_only=True):
            channel_id = int(row["id"])
            self._start_channel(channel_id)
        event("app", "V2 runtime started", channels=len(self._threads))

    def stop(self, timeout: float = 8.0) -> None:
        self.stop_event.set()
        deadline = time.monotonic() + max(0.5, float(timeout))
        for thread in list(self._threads.values()):
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(remaining)
        event("app", "V2 runtime stopped", channels=len(self._threads))

    def refresh_channels(self) -> None:
        enabled = {int(row["id"]) for row in self.store.list_channels(enabled_only=True)}
        with self._lock:
            for channel_id in enabled:
                if channel_id not in self._threads or not self._threads[channel_id].is_alive():
                    self._start_channel(channel_id)
        # Disabled channel threads exit themselves on next loop.

    def _start_channel(self, channel_id: int) -> None:
        with self._lock:
            current = self._threads.get(channel_id)
            if current and current.is_alive():
                return
            self.states[channel_id] = self.states.get(channel_id) or ChannelRuntimeState(channel_id)
            thread = threading.Thread(target=self._channel_loop, args=(channel_id,), name=f"V2-Channel-{channel_id}", daemon=True)
            self._threads[channel_id] = thread
            thread.start()

    def _channel_loop(self, channel_id: int) -> None:
        state = self.states[channel_id]
        worker_id = f"channel-{channel_id}"
        while not self.stop_event.is_set():
            channel = self.store.get_channel(channel_id)
            if channel is None or not channel.enabled:
                event("worker", "channel worker stopped because channel disabled/missing", channel_id=channel_id)
                return
            state.heartbeat_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            try:
                self._maybe_collect(channel_id, channel.poll_interval_minutes, channel.poll_immediate, state)
                worked = self._process_one(channel_id, worker_id, state)
                state.published += self.publisher.publish_ready(channel_id)
                if not worked:
                    self.stop_event.wait(1.0)
            except Exception as exc:
                state.errors += 1
                event("worker", "channel loop error", level=logging.ERROR, channel_id=channel_id, detail=str(exc)[:1200])
                self.stop_event.wait(2.0)

    def _maybe_collect(self, channel_id: int, interval_minutes: int, immediate: bool, state: ChannelRuntimeState) -> None:
        now = time.monotonic()
        interval = max(30.0, float(max(1, int(interval_minutes))) * 60.0)
        due = state.last_collect_monotonic <= 0 or now - state.last_collect_monotonic >= interval
        if not due:
            return
        result = self.ingest.collect_channel(channel_id)
        state.last_collect_monotonic = now
        event("worker", "collection cycle", channel_id=channel_id, **result)

    def _process_one(self, channel_id: int, worker_id: str, state: ChannelRuntimeState) -> bool:
        job = self.store.claim_job(channel_id=channel_id, worker_id=worker_id, lease_seconds=240)
        if job is None:
            return False
        job_id = int(job["id"]); article_id = int(job["article_id"])
        article = self.store.get_article(article_id)
        if article is None:
            self.store.cancel_job(job_id, "ARTICLE_MISSING")
            return True
        event("worker", "job start", channel_id=channel_id, article_id=article_id, job_id=job_id, attempts=int(job["attempts"] or 0))
        try:
            canonical = str(article["canonical_source_url"] or "").strip()
            if not canonical.startswith(("http://", "https://")):
                self.store.defer_job(job_id, blocked_by=BlockedBy.SOURCE, error_code="SOURCE_MISSING", detail="Немає canonical source URL", retry_seconds=1800, count_attempt=False)
                return True

            if str(article["stage"]) in {str(Stage.COLLECTED), str(Stage.EXTRACTED)}:
                self.store.update_article(article_id, stage=str(Stage.EXTRACTED))
                duplicate = self.dedupe.evaluate(article_id)
                if duplicate.relation == "DUPLICATE":
                    self.store.finish_job(job_id)
                    state.processed += 1
                    return True

            # A previous technical interruption may have left the article partially selected.
            current = self.store.get_article(article_id)
            if current is None:
                raise RuntimeError("ARTICLE_MISSING")
            if str(current["decision"]) != str(Decision.PENDING):
                self.store.finish_job(job_id)
                return True

            outcome = self.editorial.process_article(article_id)
            state.processed += 1
            self.store.finish_job(job_id)
            event("worker", "job complete", channel_id=channel_id, article_id=article_id, job_id=job_id, decision=str(outcome.decision))
            return True
        except GatewayExhausted as exc:
            blocker = BlockedBy.AI if exc.provider_outage else BlockedBy.QUALITY
            code = "WAITING_AI" if exc.provider_outage else "QUALITY_RETRY"
            retry = exc.retry_seconds if exc.provider_outage else min(3600, max(180, exc.retry_seconds * (1 + int(job["attempts"] or 0))))
            self.store.defer_job(job_id, blocked_by=blocker, error_code=code, detail=str(exc), retry_seconds=retry, count_attempt=not exc.provider_outage)
            event("worker", "job deferred", channel_id=channel_id, article_id=article_id, blocked_by=str(blocker), code=code, retry_seconds=retry, detail=str(exc)[:700])
            return True
        except RuntimeError as exc:
            if str(exc) == "SOURCE_MISSING":
                self.store.defer_job(job_id, blocked_by=BlockedBy.SOURCE, error_code="SOURCE_MISSING", detail=str(exc), retry_seconds=1800, count_attempt=False)
            else:
                self.store.defer_job(job_id, blocked_by=BlockedBy.QUALITY, error_code="PIPELINE_RETRY", detail=str(exc), retry_seconds=600, count_attempt=True)
            return True
        except Exception as exc:
            state.errors += 1
            attempts = int(job["attempts"] or 0)
            retry = min(3600, 180 * (2 ** min(4, attempts)))
            self.store.defer_job(job_id, blocked_by=BlockedBy.QUALITY, error_code="PIPELINE_EXCEPTION", detail=str(exc), retry_seconds=retry, count_attempt=True)
            event("worker", "job exception deferred", level=logging.ERROR, channel_id=channel_id, article_id=article_id, job_id=job_id, retry_seconds=retry, detail=str(exc)[:1000])
            return True

    def health_snapshot(self) -> dict:
        with self._lock:
            channels = {
                cid: {
                    "alive": bool(self._threads.get(cid) and self._threads[cid].is_alive()),
                    "heartbeat_at": state.heartbeat_at,
                    "processed": state.processed,
                    "published": state.published,
                    "errors": state.errors,
                }
                for cid, state in self.states.items()
            }
        providers = [
            {"provider": item.provider, "state": str(item.state), "model": item.model, "detail": item.detail, "cooldown_until": item.cooldown_until}
            for item in self.store.provider_health()
        ]
        return {"running": not self.stop_event.is_set(), "channels": channels, "providers": providers}
