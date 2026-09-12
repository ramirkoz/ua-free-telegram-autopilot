from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .ai_gateway import AIGateway, GatewayExhausted
from .dedupe import DedupeEngine
from .domain import BlockedBy, Decision, Stage
from .editorial import EditorialEngine
from .ingest import IngestService
from .loghub import event
from .media_pipeline import processing_media_gate
from .publisher import Publisher
from .storage import V2Store


@dataclass(slots=True)
class ChannelRuntimeState:
    channel_id: int
    last_collect_monotonic: float = 0.0
    last_publish_monotonic: float = 0.0
    last_expire_monotonic: float = 0.0
    processed: int = 0
    published: int = 0
    errors: int = 0
    jobs_started: int = 0
    jobs_completed: int = 0
    jobs_deferred: int = 0
    jobs_rejected: int = 0
    jobs_duplicates: int = 0
    jobs_expired: int = 0
    collect_cycles: int = 0
    last_collect_duration_seconds: float = 0.0
    last_collect_completed_at: str = ""
    collecting: bool = False
    collect_started_at: str = ""
    collector_heartbeat_at: str = ""
    collector_errors: int = 0
    last_job_activity_at: str = ""
    heartbeat_at: str = ""
    phase: str = "idle"
    phase_started_at: str = ""


class RuntimeEngine:
    """Clean V2 scheduler with one isolated preparation loop per channel."""

    def __init__(self, store: V2Store):
        self.store = store
        self.gateway = AIGateway(store)
        self.ingest = IngestService(store)
        self.dedupe = DedupeEngine(store)
        self.editorial = EditorialEngine(store, self.gateway)
        self.publisher = Publisher(store)
        self.stop_event = threading.Event()
        self.stop_event.set()  # not running until start() explicitly clears it
        self._threads: dict[int, threading.Thread] = {}
        self._collector_threads: dict[int, threading.Thread] = {}
        self._lock = threading.RLock()
        self.states: dict[int, ChannelRuntimeState] = {}
        self.started_at: str = ""

    @staticmethod
    def _touch(state: ChannelRuntimeState, phase: str | None = None) -> None:
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        state.heartbeat_at = stamp
        if phase is not None and phase != state.phase:
            state.phase = str(phase)
            state.phase_started_at = stamp

    @staticmethod
    def _touch_collector(state: ChannelRuntimeState) -> None:
        state.collector_heartbeat_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _job_activity(state: ChannelRuntimeState, kind: str) -> None:
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        state.last_job_activity_at = stamp
        state.heartbeat_at = stamp
        if kind == "started": state.jobs_started += 1
        elif kind == "completed": state.jobs_completed += 1
        elif kind == "deferred": state.jobs_deferred += 1
        elif kind == "rejected": state.jobs_rejected += 1
        elif kind == "duplicate": state.jobs_duplicates += 1
        elif kind == "expired": state.jobs_expired += 1

    def start(self) -> None:
        with self._lock:
            live = any(t.is_alive() for t in [*self._threads.values(), *self._collector_threads.values()])
        if live and not self.stop_event.is_set():
            event("app", "V2 runtime start ignored; already running", level=logging.WARNING)
            return
        self.store.recover_stale_leases()
        self.stop_event.clear()
        self.started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        threading.Thread(target=self._startup_ai_probe, name="V2-AI-Startup-Probe", daemon=True).start()
        for row in self.store.list_channels(enabled_only=True):
            self._start_channel(int(row["id"]))
        event("app", "V2 runtime started", channels=len(self._threads), collectors=len(self._collector_threads))

    def _startup_ai_probe(self) -> None:
        try:
            health = self.gateway.probe_all()
            healthy = sum(1 for item in health if str(item.state) == "HEALTHY")
            event("ai", "startup provider probe complete", healthy=healthy, total=len(health))
        except Exception as exc:
            event("ai", "startup provider probe failed", level=logging.WARNING, detail=str(exc)[:1000])

    def stop(self, timeout: float = 8.0) -> None:
        self.stop_event.set()
        deadline = time.monotonic() + max(0.5, float(timeout))
        threads = [*list(self._threads.values()), *list(self._collector_threads.values())]
        for thread in threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(remaining)
        lingering = [thread.name for thread in threads if thread.is_alive()]
        if lingering:
            event("app", "V2 runtime stop incomplete", level=logging.ERROR, lingering_threads=lingering, timeout_seconds=float(timeout))
        else:
            event("app", "V2 runtime stopped", channels=len(self._threads), collectors=len(self._collector_threads))

    def refresh_channels(self) -> None:
        enabled = {int(row["id"]) for row in self.store.list_channels(enabled_only=True)}
        with self._lock:
            for channel_id in enabled:
                self._start_channel(channel_id)

    def _start_channel(self, channel_id: int) -> None:
        with self._lock:
            self.states[channel_id] = self.states.get(channel_id) or ChannelRuntimeState(channel_id)
            worker = self._threads.get(channel_id)
            if not worker or not worker.is_alive():
                worker = threading.Thread(target=self._channel_loop, args=(channel_id,), name=f"V2-Channel-{channel_id}", daemon=True)
                self._threads[channel_id] = worker
                worker.start()
            collector = self._collector_threads.get(channel_id)
            if not collector or not collector.is_alive():
                collector = threading.Thread(target=self._collector_loop, args=(channel_id,), name=f"V2-Collector-{channel_id}", daemon=True)
                self._collector_threads[channel_id] = collector
                collector.start()

    def _channel_loop(self, channel_id: int) -> None:
        """Processing/publishing loop. Collection is deliberately isolated in RC8."""
        state = self.states[channel_id]
        worker_id = f"channel-{channel_id}"
        while not self.stop_event.is_set():
            channel = self.store.get_channel(channel_id)
            if channel is None or not channel.enabled:
                event("worker", "channel worker stopped because channel disabled/missing", channel_id=channel_id)
                return
            self._touch(state, "loop")
            try:
                self._maybe_expire_stale(channel_id, channel.max_age_hours, state)
                self._touch(state, "process")
                worked = self._process_one(channel_id, worker_id, state)
                self._touch(state, "publish")
                state.published += self.publisher.publish_ready(channel_id, heartbeat=lambda: self._touch(state, "publish"))
                self._touch(state, "idle")
                if not worked:
                    self.stop_event.wait(0.75)
            except Exception as exc:
                state.errors += 1
                event("worker", "channel loop error", level=logging.ERROR, channel_id=channel_id, detail=str(exc)[:1200])
                self.stop_event.wait(2.0)

    def _collector_loop(self, channel_id: int) -> None:
        """Independent collector so a slow 10-15 minute crawl cannot freeze processing/publish."""
        state = self.states[channel_id]
        while not self.stop_event.is_set():
            channel = self.store.get_channel(channel_id)
            if channel is None or not channel.enabled:
                event("worker", "channel collector stopped because channel disabled/missing", channel_id=channel_id)
                state.collecting = False
                return
            interval = max(30.0, float(max(1, int(channel.poll_interval_minutes))) * 60.0)
            now = time.monotonic()
            due = state.last_collect_monotonic <= 0 or now - state.last_collect_monotonic >= interval
            if not due:
                self._touch_collector(state)
                remaining = max(0.25, interval - (now - state.last_collect_monotonic))
                self.stop_event.wait(min(1.0, remaining))
                continue

            started = time.monotonic()
            state.collecting = True
            state.collect_started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            self._touch_collector(state)
            try:
                result = self.ingest.collect_channel(channel_id, heartbeat=lambda: self._touch_collector(state))
                finished = time.monotonic()
                state.last_collect_monotonic = finished
                state.collect_cycles += 1
                state.last_collect_duration_seconds = round(max(0.0, finished - started), 2)
                state.last_collect_completed_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                event("worker", "collection cycle", channel_id=channel_id, duration_seconds=state.last_collect_duration_seconds, **result)
            except Exception as exc:
                finished = time.monotonic()
                state.last_collect_monotonic = finished
                state.last_collect_duration_seconds = round(max(0.0, finished - started), 2)
                state.collector_errors += 1
                event("worker", "collector loop error", level=logging.ERROR, channel_id=channel_id, detail=str(exc)[:1200], duration_seconds=state.last_collect_duration_seconds)
                self.stop_event.wait(2.0)
            finally:
                state.collecting = False
                self._touch_collector(state)

    def _maybe_expire_stale(self, channel_id: int, max_age_hours: int, state: ChannelRuntimeState) -> None:
        now = time.monotonic()
        if state.last_expire_monotonic > 0 and now - state.last_expire_monotonic < 60.0:
            return
        state.last_expire_monotonic = now
        expired = self.store.expire_stale_jobs(channel_id, max_age_hours)
        if expired:
            state.jobs_expired += int(expired)
            state.last_job_activity_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            event("worker", "stale jobs expired", channel_id=channel_id, count=int(expired), max_age_hours=int(max_age_hours or 0))

    def _process_one(self, channel_id: int, worker_id: str, state: ChannelRuntimeState) -> bool:
        job = self.store.claim_job(channel_id=channel_id, worker_id=worker_id, lease_seconds=240)
        if job is None:
            return False
        job_id = int(job["id"])
        article_id = int(job["article_id"])
        article = self.store.get_article(article_id)
        if article is None:
            self.store.cancel_job(job_id, "ARTICLE_MISSING")
            self._job_activity(state, "completed")
            return True
        self._job_activity(state, "started")
        event("worker", "job start", channel_id=channel_id, article_id=article_id, job_id=job_id, attempts=int(job["attempts"] or 0))
        try:
            canonical = str(article["canonical_source_url"] or "").strip()
            if not canonical.startswith(("http://", "https://")):
                self.store.defer_job(job_id, blocked_by=BlockedBy.SOURCE, error_code="SOURCE_MISSING", detail="Немає canonical source URL", retry_seconds=1800, count_attempt=False)
                self._job_activity(state, "deferred")
                return True

            if str(article["stage"]) in {str(Stage.COLLECTED), str(Stage.EXTRACTED)}:
                self.store.update_article(article_id, stage=str(Stage.EXTRACTED))
                duplicate = self.dedupe.evaluate(article_id)
                if duplicate.relation == "DUPLICATE":
                    self.store.finish_job(job_id)
                    state.processed += 1
                    self._job_activity(state, "duplicate")
                    self._job_activity(state, "completed")
                    return True

            current = self.store.get_article(article_id)
            if current is None:
                raise RuntimeError("ARTICLE_MISSING")
            channel = self.store.get_channel(channel_id)
            if channel is None:
                raise RuntimeError("CHANNEL_MISSING")
            media_ok, media_reason = processing_media_gate(channel, current)
            if not media_ok:
                self.store.defer_job(job_id, blocked_by=BlockedBy.MEDIA, error_code=media_reason, detail="Monitoring channel requires valid media before AI processing", retry_seconds=300, count_attempt=False)
                self._job_activity(state, "deferred")
                event("media", "required monitoring item deferred before AI", level=logging.WARNING, channel_id=channel_id, article_id=article_id, code=media_reason)
                return True
            if str(current["decision"]) != str(Decision.PENDING):
                self.store.finish_job(job_id)
                self._job_activity(state, "completed")
                return True

            outcome = self.editorial.process_article(article_id, heartbeat=lambda: self._touch(state, "process"))
            state.processed += 1
            self.store.finish_job(job_id)
            if str(outcome.decision) == str(Decision.REJECT):
                self._job_activity(state, "rejected")
            self._job_activity(state, "completed")
            event("worker", "job complete", channel_id=channel_id, article_id=article_id, job_id=job_id, decision=str(outcome.decision))
            return True
        except GatewayExhausted as exc:
            blocker = BlockedBy.AI if exc.provider_outage else BlockedBy.QUALITY
            code = "WAITING_AI" if exc.provider_outage else "QUALITY_RETRY"
            retry = exc.retry_seconds if exc.provider_outage else min(3600, max(180, exc.retry_seconds * (1 + int(job["attempts"] or 0))))
            self.store.defer_job(job_id, blocked_by=blocker, error_code=code, detail=str(exc), retry_seconds=retry, count_attempt=not exc.provider_outage)
            self._job_activity(state, "deferred")
            event("worker", "job deferred", channel_id=channel_id, article_id=article_id, blocked_by=str(blocker), code=code, retry_seconds=retry, detail=str(exc)[:700])
            return True
        except RuntimeError as exc:
            if str(exc) == "SOURCE_MISSING":
                self.store.defer_job(job_id, blocked_by=BlockedBy.SOURCE, error_code="SOURCE_MISSING", detail=str(exc), retry_seconds=1800, count_attempt=False)
            else:
                self.store.defer_job(job_id, blocked_by=BlockedBy.QUALITY, error_code="PIPELINE_RETRY", detail=str(exc), retry_seconds=600, count_attempt=True)
            self._job_activity(state, "deferred")
            return True
        except Exception as exc:
            state.errors += 1
            attempts = int(job["attempts"] or 0)
            retry = min(3600, 180 * (2 ** min(4, attempts)))
            self.store.defer_job(job_id, blocked_by=BlockedBy.QUALITY, error_code="PIPELINE_EXCEPTION", detail=str(exc), retry_seconds=retry, count_attempt=True)
            self._job_activity(state, "deferred")
            event("worker", "job exception deferred", level=logging.ERROR, channel_id=channel_id, article_id=article_id, job_id=job_id, retry_seconds=retry, detail=str(exc)[:1000])
            return True

    def health_snapshot(self) -> dict:
        with self._lock:
            channels = {
                cid: {
                    "alive": bool(self._threads.get(cid) and self._threads[cid].is_alive()),
                    "collector_alive": bool(self._collector_threads.get(cid) and self._collector_threads[cid].is_alive()),
                    "heartbeat_at": state.heartbeat_at,
                    "collector_heartbeat_at": state.collector_heartbeat_at,
                    "processed": state.processed,
                    "published": state.published,
                    "errors": state.errors,
                    "jobs_started": state.jobs_started,
                    "jobs_completed": state.jobs_completed,
                    "jobs_deferred": state.jobs_deferred,
                    "jobs_rejected": state.jobs_rejected,
                    "jobs_duplicates": state.jobs_duplicates,
                    "jobs_expired": state.jobs_expired,
                    "last_job_activity_at": state.last_job_activity_at,
                    "collect_cycles": state.collect_cycles,
                    "last_collect_duration_seconds": state.last_collect_duration_seconds,
                    "last_collect_completed_at": state.last_collect_completed_at,
                    "collecting": state.collecting,
                    "collect_started_at": state.collect_started_at,
                    "collector_errors": state.collector_errors,
                    "phase": state.phase,
                    "phase_started_at": state.phase_started_at,
                }
                for cid, state in self.states.items()
            }
        providers = [
            {"provider": item.provider, "state": str(item.state), "model": item.model, "detail": item.detail, "cooldown_until": item.cooldown_until}
            for item in self.store.provider_health()
        ]
        models = [
            {
                "provider": item.provider, "model": item.model, "state": str(item.state), "detail": item.detail,
                "cooldown_until": item.cooldown_until, "success_count": item.success_count, "failure_count": item.failure_count,
            }
            for item in self.store.ai_model_health()
        ]
        live_workers = sum(1 for cid in self.states if self._threads.get(cid) and self._threads[cid].is_alive())
        live_collectors = sum(1 for cid in self.states if self._collector_threads.get(cid) and self._collector_threads[cid].is_alive())
        stop_requested = self.stop_event.is_set()
        return {
            "running": bool(live_workers or live_collectors or not stop_requested),
            "stop_requested": stop_requested,
            "live_workers": live_workers,
            "live_collectors": live_collectors,
            "started_at": self.started_at, "channels": channels, "providers": providers, "models": models,
        }
