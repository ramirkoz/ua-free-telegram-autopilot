from __future__ import annotations

import json
import os
import re
from email.utils import parsedate_to_datetime
import shutil
import sqlite3
import threading
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import V2_VERSION
from .loghub import event
from .media_pipeline import build_media_bundle
from .storage import V2Store, now_iso


@dataclass(slots=True)
class SupervisorConfig:
    enabled: bool = True
    mirror_dir: str = ""
    interval_seconds: int = 30
    ai_grace_seconds: int = 300
    worker_stale_seconds: int = 180
    queue_stall_seconds: int = 900
    disk_min_free_mb: int = 1024

    def normalized(self) -> "SupervisorConfig":
        return SupervisorConfig(
            enabled=bool(self.enabled),
            mirror_dir=str(self.mirror_dir or "").strip(),
            interval_seconds=max(15, min(600, int(self.interval_seconds or 30))),
            ai_grace_seconds=max(30, min(7200, int(self.ai_grace_seconds or 300))),
            worker_stale_seconds=max(60, min(7200, int(self.worker_stale_seconds or 180))),
            queue_stall_seconds=max(120, min(21600, int(self.queue_stall_seconds or 900))),
            disk_min_free_mb=max(128, min(102400, int(self.disk_min_free_mb or 1024))),
        )


@dataclass(frozen=True, slots=True)
class Incident:
    severity: str
    code: str
    title: str
    detail: str


class SupervisorService:
    """Out-of-band observability for the clean V2 runtime.

    It deliberately does not make editorial decisions and does not restart the
    application.  Its job is to make failures visible, preserve a compact
    diagnostic snapshot, and feed an external/ChatGPT supervisor through a
    normal filesystem folder (typically a Google Drive Desktop synced folder).
    """

    def __init__(self, store: V2Store, runtime: Any, logs_dir: str | Path):
        self.store = store
        self.runtime = runtime
        self.logs_dir = Path(logs_dir)
        self.root = self.store.path.parent / "supervisor"
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / "config.json"
        self.status_path = self.root / "status.json"
        self.incident_path = self.root / "incident.json"
        self.recent_events_path = self.root / "recent_events.json"
        self._config = self.load_config()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._expected_running = False
        self._first_seen: dict[str, float] = {}
        self._active_codes: set[str] = set()
        self._last_snapshot: dict[str, Any] = {}
        self._last_incidents: list[Incident] = []

    @property
    def config(self) -> SupervisorConfig:
        with self._lock:
            return self._config

    def load_config(self) -> SupervisorConfig:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                allowed = set(SupervisorConfig.__dataclass_fields__)
                return SupervisorConfig(**{k: data[k] for k in data if k in allowed}).normalized()
        except FileNotFoundError:
            pass
        except Exception as exc:
            event("supervisor", "supervisor config read failed", level=30, detail=str(exc)[:800])
        return SupervisorConfig()

    def save_config(self, config: SupervisorConfig) -> SupervisorConfig:
        cfg = config.normalized()
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_json(self.config_path, asdict(cfg))
        with self._lock:
            self._config = cfg
        return cfg

    def set_expected_running(self, value: bool) -> None:
        with self._lock:
            self._expected_running = bool(value)
        # Emit the new intended state immediately so the external supervisor
        # never interprets a deliberate Stop as a crash.
        try:
            self.write_snapshot()
        except Exception:
            pass

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="V2-Supervisor", daemon=True)
            self._thread.start()
        event("supervisor", "supervisor service started")

    def stop(self, timeout: float = 4.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(max(0.2, float(timeout)))
        event("supervisor", "supervisor service stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                cfg = self.config
                if cfg.enabled:
                    snapshot = self.write_snapshot()
                    incidents = self.evaluate(snapshot, cfg)
                    self._handle_incidents(snapshot, incidents, cfg)
            except Exception as exc:
                event("supervisor", "supervisor tick failed", level=40, detail=str(exc)[:1200])
            elapsed = time.monotonic() - started
            self._stop.wait(max(1.0, float(self.config.interval_seconds) - elapsed))

    def _queue_snapshot(self) -> dict[str, Any]:
        with self.store.connect() as con:
            rows = con.execute("SELECT state,COUNT(*) n FROM jobs GROUP BY state").fetchall()
            states = {str(r["state"]): int(r["n"] or 0) for r in rows}
            blockers = {
                str(r["blocked_by"]): int(r["n"] or 0)
                for r in con.execute(
                    """
                    SELECT a.blocked_by,COUNT(DISTINCT j.article_id) n
                    FROM jobs j JOIN articles a ON a.id=j.article_id
                    WHERE j.state IN ('QUEUED','WAITING','LEASED')
                      AND a.blocked_by <> 'NONE'
                    GROUP BY a.blocked_by
                    """
                )
            }
            active = int(con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','WAITING','LEASED')").fetchone()[0] or 0)
            due = int(con.execute("SELECT COUNT(*) FROM jobs WHERE state='QUEUED' AND available_at<=?", (now_iso(),)).fetchone()[0] or 0)
            last_job_update = str(con.execute("SELECT COALESCE(MAX(updated_at),'') FROM jobs").fetchone()[0] or "")
            published_total = int(con.execute("SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED'").fetchone()[0] or 0)
            published_today = int(
                con.execute(
                    "SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED' AND substr(published_at,1,10)=?",
                    (datetime.now().astimezone().date().isoformat(),),
                ).fetchone()[0]
                or 0
            )
            last_publish = str(con.execute("SELECT COALESCE(MAX(published_at),'') FROM articles WHERE stage='PUBLISHED'").fetchone()[0] or "")
            recent_errors = int(
                con.execute(
                    "SELECT COUNT(*) FROM jobs WHERE error_code<>'' AND updated_at>=?",
                    (datetime.fromtimestamp(time.time() - 600, tz=timezone.utc).astimezone().isoformat(timespec="seconds"),),
                ).fetchone()[0]
                or 0
            )
        return {
            "states": states,
            "blockers": blockers,
            "active": active,
            "due": due,
            "last_job_update": last_job_update,
            "published_total": published_total,
            "published_today": published_today,
            "last_publish": last_publish,
            "recent_errors_10m": recent_errors,
        }

    def _media_snapshot(self) -> dict[str, Any]:
        """Detect actual publication loss, not raw source URL variants.

        RC16 compared ``telegram_media_count`` to raw/declared ingest counts. One
        visual image exposed through several signed/resized URLs therefore looked
        like a media loss even when the deduplicated publication was complete.
        RC17 prefers the expected count persisted by the publisher and otherwise
        falls back to the deduplicated publication bundle.
        """
        cut60 = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT id,channel_id,title,published_at,telegram_media_count,media_json,article_layout_json
                   FROM articles WHERE stage='PUBLISHED' AND datetime(published_at)>=datetime(?)
                   ORDER BY datetime(published_at) DESC,id DESC LIMIT 200""", (cut60,)
            ).fetchall()
        lost: list[dict[str, Any]] = []
        for row in rows:
            expected = 0
            try:
                layout = json.loads(str(row["article_layout_json"] or "{}"))
                if isinstance(layout, dict):
                    delivery = layout.get("telegram_delivery")
                    if isinstance(delivery, dict):
                        expected = int(delivery.get("expected_media_count") or delivery.get("media_count") or 0)
            except Exception:
                expected = 0
            if expected <= 0:
                try:
                    expected = int(build_media_bundle(row).count)
                except Exception:
                    expected = 0
            sent = int(row["telegram_media_count"] or 0)
            if expected > sent:
                lost.append({
                    "article_id": int(row["id"]), "channel_id": int(row["channel_id"]),
                    "title": str(row["title"] or "")[:220], "source_media_count": expected,
                    "published_media_count": sent, "published_at": str(row["published_at"] or ""),
                })
        filtered_articles = 0
        raw_candidates = discarded_non_content = discarded_video_thumb = discarded_duplicate = content_media = 0
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT article_layout_json FROM articles
                   WHERE discovered_at>=? ORDER BY id DESC LIMIT 500""", (cut60,)
            ).fetchall()
        for item in rows:
            try:
                layout=json.loads(str(item["article_layout_json"] or "{}"))
                tg=layout.get("telegram") if isinstance(layout,dict) else None
                filt=tg.get("media_filter") if isinstance(tg,dict) else None
                if not isinstance(filt,dict):
                    continue
                raw_candidates += int(filt.get("raw_candidates") or 0)
                discarded_non_content += int(filt.get("discarded_non_content") or 0)
                discarded_video_thumb += int(filt.get("discarded_video_thumb") or 0)
                discarded_duplicate += int(filt.get("discarded_duplicate") or 0)
                content_media += int(filt.get("content_media") or 0)
                if int(filt.get("discarded_non_content") or 0) or int(filt.get("discarded_video_thumb") or 0):
                    filtered_articles += 1
            except Exception:
                continue
        return {
            "lost_last_60m": len(lost), "items": lost[:20],
            "telegram_filter_last_60m": {
                "articles": filtered_articles, "raw_candidates": raw_candidates,
                "discarded_non_content": discarded_non_content,
                "discarded_video_thumb": discarded_video_thumb,
                "discarded_duplicate": discarded_duplicate, "content_media": content_media,
            },
        }

    def _channel_stats(self) -> dict[str, Any]:
        now_value = now_iso()
        now_ts = time.time()
        today = datetime.now().astimezone().date().isoformat()
        cut15 = datetime.fromtimestamp(now_ts - 900, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        cut10 = datetime.fromtimestamp(now_ts - 600, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        cut30 = datetime.fromtimestamp(now_ts - 1800, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        cut60 = datetime.fromtimestamp(now_ts - 3600, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        out: dict[str, Any] = {}
        with self.store.connect() as con:
            for ch in con.execute("SELECT id,name,enabled,max_age_hours FROM channels WHERE enabled=1 ORDER BY id").fetchall():
                cid = int(ch["id"])
                active = int(con.execute("SELECT COUNT(*) FROM jobs WHERE channel_id=? AND state IN ('QUEUED','WAITING','LEASED')", (cid,)).fetchone()[0] or 0)
                due = int(con.execute("SELECT COUNT(*) FROM jobs WHERE channel_id=? AND state='QUEUED' AND available_at<=?", (cid, now_value)).fetchone()[0] or 0)
                last_job_activity = str(con.execute("SELECT COALESCE(MAX(updated_at),'') FROM jobs WHERE channel_id=?", (cid,)).fetchone()[0] or "")
                last_active_job_update = str(con.execute("SELECT COALESCE(MAX(updated_at),'') FROM jobs WHERE channel_id=? AND state IN ('QUEUED','WAITING','LEASED')", (cid,)).fetchone()[0] or "")
                oldest_due = str(con.execute(
                    """SELECT COALESCE(MIN(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END),'')
                       FROM jobs j JOIN articles a ON a.id=j.article_id
                       WHERE j.channel_id=? AND j.state='QUEUED' AND j.available_at<=?""",
                    (cid, now_value),
                ).fetchone()[0] or "")
                oldest_ts = self._parse_iso(oldest_due)
                oldest_due_age_seconds = int(max(0.0, now_ts - oldest_ts)) if oldest_ts is not None else 0
                blockers = {
                    str(r["blocked_by"]): int(r["n"] or 0)
                    for r in con.execute(
                        """SELECT a.blocked_by,COUNT(DISTINCT j.article_id) n FROM jobs j JOIN articles a ON a.id=j.article_id
                           WHERE j.channel_id=? AND j.state IN ('QUEUED','WAITING','LEASED') AND a.blocked_by<>'NONE' GROUP BY a.blocked_by""",
                        (cid,),
                    )
                }
                ready = int(con.execute("SELECT COUNT(*) FROM articles WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'", (cid,)).fetchone()[0] or 0)
                oldest_ready = str(con.execute("SELECT COALESCE(MIN(ready_at),'') FROM articles WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'", (cid,)).fetchone()[0] or "")
                oldest_ready_ts = self._parse_iso(oldest_ready)
                oldest_ready_age_seconds = int(max(0.0, now_ts - oldest_ready_ts)) if oldest_ready_ts is not None else 0
                published_total = int(con.execute("SELECT COUNT(*) FROM articles WHERE channel_id=? AND stage='PUBLISHED'", (cid,)).fetchone()[0] or 0)
                published_today = int(con.execute("SELECT COUNT(*) FROM articles WHERE channel_id=? AND stage='PUBLISHED' AND substr(published_at,1,10)=?", (cid, today)).fetchone()[0] or 0)
                last_publish = str(con.execute("SELECT COALESCE(MAX(published_at),'') FROM articles WHERE channel_id=? AND stage='PUBLISHED'", (cid,)).fetchone()[0] or "")
                published_30m = int(con.execute("SELECT COUNT(*) FROM articles WHERE channel_id=? AND stage='PUBLISHED' AND datetime(published_at)>=datetime(?)", (cid, cut30)).fetchone()[0] or 0)
                published_60m = int(con.execute("SELECT COUNT(*) FROM articles WHERE channel_id=? AND stage='PUBLISHED' AND datetime(published_at)>=datetime(?)", (cid, cut60)).fetchone()[0] or 0)
                jobs_done_10m = int(con.execute("SELECT COUNT(*) FROM jobs WHERE channel_id=? AND state='DONE' AND datetime(updated_at)>=datetime(?)", (cid, cut10)).fetchone()[0] or 0)
                jobs_done_30m = int(con.execute("SELECT COUNT(*) FROM jobs WHERE channel_id=? AND state='DONE' AND datetime(updated_at)>=datetime(?)", (cid, cut30)).fetchone()[0] or 0)
                jobs_done_60m = int(con.execute("SELECT COUNT(*) FROM jobs WHERE channel_id=? AND state='DONE' AND datetime(updated_at)>=datetime(?)", (cid, cut60)).fetchone()[0] or 0)
                jobs_waiting_10m = int(con.execute("SELECT COUNT(*) FROM jobs WHERE channel_id=? AND state='WAITING' AND datetime(updated_at)>=datetime(?)", (cid, cut10)).fetchone()[0] or 0)
                rejected_30m = int(con.execute("""SELECT COUNT(*) FROM jobs j JOIN articles a ON a.id=j.article_id
                    WHERE j.channel_id=? AND j.state='DONE' AND a.decision='REJECT' AND datetime(j.updated_at)>=datetime(?)""", (cid, cut30)).fetchone()[0] or 0)
                duplicates_30m = int(con.execute("""SELECT COUNT(*) FROM jobs j JOIN articles a ON a.id=j.article_id
                    WHERE j.channel_id=? AND j.state='DONE' AND a.decision='DUPLICATE' AND datetime(j.updated_at)>=datetime(?)""", (cid, cut30)).fetchone()[0] or 0)
                sources_total = int(con.execute("SELECT COUNT(*) FROM sources WHERE channel_id=? AND enabled=1", (cid,)).fetchone()[0] or 0)
                recent_source_errors = int(con.execute("SELECT COUNT(*) FROM sources WHERE channel_id=? AND enabled=1 AND last_error<>'' AND last_checked_at>=?", (cid, cut15)).fetchone()[0] or 0)
                last_source_check = str(con.execute("SELECT COALESCE(MAX(last_checked_at),'') FROM sources WHERE channel_id=? AND enabled=1", (cid,)).fetchone()[0] or "")
                sources_cooling_down = int(con.execute("""SELECT COUNT(*) FROM source_health sh JOIN sources s ON s.id=sh.source_id
                    WHERE s.channel_id=? AND s.enabled=1 AND sh.cooldown_until<>'' AND datetime(sh.cooldown_until)>datetime(?)""", (cid, now_value)).fetchone()[0] or 0)
                health_rows = con.execute("""SELECT s.name,sh.last_duration_ms,sh.consecutive_failures,sh.cooldown_until,sh.last_outcome
                    FROM source_health sh JOIN sources s ON s.id=sh.source_id WHERE s.channel_id=? AND s.enabled=1
                    ORDER BY sh.last_duration_ms DESC LIMIT 5""", (cid,)).fetchall()
                slow_sources = [
                    {"name": str(r["name"]), "duration_ms": int(r["last_duration_ms"] or 0), "failures": int(r["consecutive_failures"] or 0), "cooldown_until": str(r["cooldown_until"] or ""), "outcome": str(r["last_outcome"] or "")}
                    for r in health_rows
                ]
                out[str(cid)] = {
                    "name": str(ch["name"]),
                    "max_age_hours": int(ch["max_age_hours"] or 0),
                    "active_jobs": active,
                    "due_jobs": due,
                    "last_job_update": last_job_activity,
                    "last_job_activity": last_job_activity,
                    "last_active_job_update": last_active_job_update,
                    "oldest_due": oldest_due,
                    "oldest_due_age_seconds": oldest_due_age_seconds,
                    "blockers": blockers,
                    "ready": ready,
                    "oldest_ready": oldest_ready,
                    "oldest_ready_age_seconds": oldest_ready_age_seconds,
                    "published_total": published_total,
                    "published_today": published_today,
                    "published_30m": published_30m,
                    "published_60m": published_60m,
                    "last_publish": last_publish,
                    "jobs_done_10m": jobs_done_10m,
                    "jobs_done_30m": jobs_done_30m,
                    "jobs_done_60m": jobs_done_60m,
                    "jobs_waiting_10m": jobs_waiting_10m,
                    "rejected_30m": rejected_30m,
                    "duplicates_30m": duplicates_30m,
                    "sources_total": sources_total,
                    "recent_source_errors_15m": recent_source_errors,
                    "sources_cooling_down": sources_cooling_down,
                    "slow_sources": slow_sources,
                    "last_source_check": last_source_check,
                }
        return out

    def _operational_states(self, snapshot: dict[str, Any], cfg: SupervisorConfig) -> dict[str, dict[str, Any]]:
        now = time.time()
        started = self._parse_iso(str(snapshot.get("runtime_started_at") or ""))
        runtime_age = max(0.0, now - started) if started is not None else 0.0
        channels = {str(k): v for k, v in dict(snapshot.get("channels") or {}).items()}
        stats_all = dict(snapshot.get("channel_stats") or {})
        result: dict[str, dict[str, Any]] = {}
        for cid, stats in stats_all.items():
            state = dict(channels.get(str(cid)) or {})
            due = int(stats.get("due_jobs") or 0)
            reasons: list[str] = []
            if not bool(state.get("alive")):
                result[str(cid)] = {"state": "DEAD", "reasons": ["worker not alive"]}
                continue

            last_candidates = [
                self._parse_iso(str(state.get("last_job_activity_at") or "")),
                self._parse_iso(str(stats.get("last_job_activity") or "")),
            ]
            last_job = max((x for x in last_candidates if x is not None), default=None)
            hb = self._parse_iso(str(state.get("heartbeat_at") or ""))
            fresh_heartbeat = hb is not None and now - hb <= cfg.worker_stale_seconds
            startup_grace = runtime_age < max(600.0, float(cfg.queue_stall_seconds))
            true_stall = bool(
                due > 0 and not startup_grace and last_job is not None
                and now - last_job >= cfg.queue_stall_seconds
                and fresh_heartbeat
            )
            if true_stall:
                result[str(cid)] = {"state": "STALLED", "reasons": [f"no job activity for {int(now-last_job)}s"]}
                continue

            done30 = int(stats.get("jobs_done_30m") or 0)
            published30 = int(stats.get("published_30m") or 0)
            ready = int(stats.get("ready") or 0)
            oldest_age = int(stats.get("oldest_due_age_seconds") or 0)
            oldest_ready_age = int(stats.get("oldest_ready_age_seconds") or 0)
            max_age_hours = max(1, int(stats.get("max_age_hours") or 24))
            cooling = int(stats.get("sources_cooling_down") or 0)
            total_sources = int(stats.get("sources_total") or 0)
            source_errors = int(stats.get("recent_source_errors_15m") or 0)

            if not bool(state.get("collector_alive", True)):
                reasons.append("collector not alive")
            if due >= 100 and oldest_age >= 3600 and done30 < 3:
                reasons.append(f"low processing throughput: {done30} jobs done/30m")
            if due >= 100 and int(stats.get("published_60m") or 0) == 0:
                reasons.append(f"no publications/60m with due backlog={due}")
            if ready >= 5 and oldest_ready_age >= 900 and published30 == 0:
                reasons.append(f"READY backlog: {ready} with no publications/30m")
            near_ttl = max_age_hours * 3600 * 0.85
            if due >= 50 and oldest_age >= near_ttl:
                reasons.append(f"oldest due near TTL: {oldest_age//60}m/{max_age_hours*60}m")
            if total_sources >= 5 and (cooling >= max(3, total_sources // 5) or source_errors >= max(4, total_sources // 4)):
                reasons.append(f"source degradation: errors={source_errors}, cooldown={cooling}/{total_sources}")
            slow = list(stats.get("slow_sources") or [])
            very_slow = [x for x in slow if int(x.get("duration_ms") or 0) >= 120000]
            if very_slow:
                reasons.append("slow source >120s: " + ", ".join(str(x.get("name") or "?") for x in very_slow[:3]))

            result[str(cid)] = {"state": "DEGRADED" if reasons else "HEALTHY", "reasons": reasons}
        return result

    def _database_status(self) -> dict[str, Any]:
        try:
            with self.store.connect() as con:
                result = str(con.execute("PRAGMA quick_check").fetchone()[0])
            return {"ok": result.casefold() == "ok", "detail": result}
        except sqlite3.Error as exc:
            return {"ok": False, "detail": str(exc)[:500]}

    def build_snapshot(self) -> dict[str, Any]:
        runtime = self.runtime.health_snapshot()
        enabled_rows = self.store.list_channels(enabled_only=True)
        enabled = {str(int(r["id"])): str(r["name"]) for r in enabled_rows}
        providers = list(runtime.get("providers") or [])
        healthy = sum(1 for p in providers if str(p.get("state")) == "HEALTHY")
        free = shutil.disk_usage(self.store.path.parent).free
        queue = self._queue_snapshot()
        with self._lock:
            expected = self._expected_running
        ai_blocked = int(dict(queue.get("blockers") or {}).get("AI", 0) or 0)
        ai_total = len(providers)
        ai_state = "UNKNOWN" if ai_total <= 0 else ("DOWN" if healthy <= 0 else ("HEALTHY" if healthy >= ai_total else "DEGRADED"))
        snapshot = {
            "schema": "ua-free-autopilot-supervisor-v2",
            "version": V2_VERSION,
            "generated_at": now_iso(),
            "expected_running": expected,
            "runtime_running": bool(runtime.get("running")),
            "runtime_stop_requested": bool(runtime.get("stop_requested")),
            "live_workers": int(runtime.get("live_workers") or 0),
            "live_collectors": int(runtime.get("live_collectors") or 0),
            "runtime_started_at": str(runtime.get("started_at") or ""),
            "enabled_channels": enabled,
            "channels": runtime.get("channels") or {},
            "providers": providers,
            "models": list(runtime.get("models") or []),
            "ai": {"healthy": healthy, "total": ai_total, "state": ai_state, "blocked_jobs": ai_blocked},
            "queue": queue,
            "media": self._media_snapshot(),
            "channel_stats": self._channel_stats(),
            "database": self._database_status(),
            "disk": {"free_bytes": int(free), "free_mb": int(free // (1024 * 1024))},
        }
        snapshot["operational_states"] = self._operational_states(snapshot, self.config.normalized())
        return snapshot

    def write_snapshot(self) -> dict[str, Any]:
        snapshot = self.build_snapshot()
        self._atomic_json(self.status_path, snapshot)
        self._mirror_file(self.status_path, "status.json")
        recent_payload = {
            "generated_at": now_iso(),
            "version": V2_VERSION,
            "events": self._recent_audit_events(250),
        }
        self._atomic_json(self.recent_events_path, recent_payload)
        self._mirror_file(self.recent_events_path, "recent_events.json")
        with self._lock:
            self._last_snapshot = snapshot
        return snapshot

    @staticmethod
    def _parse_iso(value: str) -> float | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            try:
                dt = parsedate_to_datetime(raw)
            except Exception:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    def _condition_elapsed(self, code: str, active: bool, now: float) -> float:
        if not active:
            self._first_seen.pop(code, None)
            return 0.0
        first = self._first_seen.setdefault(code, now)
        return max(0.0, now - first)

    def evaluate(self, snapshot: dict[str, Any], cfg: SupervisorConfig | None = None) -> list[Incident]:
        cfg = (cfg or self.config).normalized()
        now = time.time()
        incidents: list[Incident] = []
        expected = bool(snapshot.get("expected_running"))
        enabled: dict[str, str] = dict(snapshot.get("enabled_channels") or {})
        channels: dict[str, Any] = {str(k): v for k, v in dict(snapshot.get("channels") or {}).items()}
        queue = dict(snapshot.get("queue") or {})
        healthy = int(dict(snapshot.get("ai") or {}).get("healthy") or 0)
        runtime_running = bool(snapshot.get("runtime_running"))
        live_threads = int(snapshot.get("live_workers") or 0) + int(snapshot.get("live_collectors") or 0)
        operational = bool(expected or runtime_running or live_threads)

        lifecycle_bad = bool((expected and not runtime_running) or ((not expected) and live_threads > 0))
        elapsed_lifecycle = self._condition_elapsed("RUNTIME_LIFECYCLE_MISMATCH", lifecycle_bad, now)
        if lifecycle_bad and elapsed_lifecycle >= 60:
            incidents.append(Incident(
                "CRITICAL", "RUNTIME_LIFECYCLE_MISMATCH", "Runtime і worker lifecycle розійшлися",
                f"expected_running={expected}; runtime_running={runtime_running}; live_threads={live_threads}; stop_requested={snapshot.get('runtime_stop_requested')}."
            ))

        if not bool(dict(snapshot.get("database") or {}).get("ok", False)):
            incidents.append(Incident("CRITICAL", "DATABASE", "SQLite не пройшла quick_check", str(dict(snapshot.get("database") or {}).get("detail") or "")))

        disk_mb = int(dict(snapshot.get("disk") or {}).get("free_mb") or 0)
        if disk_mb < cfg.disk_min_free_mb:
            incidents.append(Incident("CRITICAL", "DISK_LOW", "Закінчується місце на диску", f"Вільно {disk_mb} МБ; поріг {cfg.disk_min_free_mb} МБ."))

        if expected:
            missing_or_dead: list[str] = []
            stale: list[str] = []
            for cid, name in enabled.items():
                state = channels.get(str(cid)) or {}
                if not bool(state.get("alive")):
                    missing_or_dead.append(name)
                    continue
                stats = dict(dict(snapshot.get("channel_stats") or {}).get(str(cid)) or {})
                stamps = [
                    self._parse_iso(str(state.get("heartbeat_at") or "")),
                    self._parse_iso(str(state.get("collector_heartbeat_at") or "")),
                    self._parse_iso(str(stats.get("last_job_update") or "")),
                    self._parse_iso(str(stats.get("last_source_check") or "")),
                ]
                fresh = max((stamp for stamp in stamps if stamp is not None), default=None)
                if fresh is None or now - fresh > cfg.worker_stale_seconds:
                    phase = str(state.get("phase") or "").strip()
                    stale.append(f"{name}" + (f" [{phase}]" if phase else ""))
            elapsed = self._condition_elapsed("WORKER_DEAD", bool(missing_or_dead), now)
            if missing_or_dead and elapsed >= cfg.worker_stale_seconds:
                incidents.append(Incident("CRITICAL", "WORKER_DEAD", "Worker каналу не працює", ", ".join(missing_or_dead)))
            elapsed = self._condition_elapsed("WORKER_STALE", bool(stale), now)
            if stale and elapsed >= cfg.worker_stale_seconds:
                incidents.append(Incident("CRITICAL", "WORKER_STALE", "Heartbeat worker застарів", ", ".join(stale)))
        else:
            self._condition_elapsed("WORKER_DEAD", False, now)
            self._condition_elapsed("WORKER_STALE", False, now)

        active = int(queue.get("active") or 0)
        due = int(queue.get("due") or 0)
        ai_blocked = int(dict(queue.get("blockers") or {}).get("AI", 0) or 0)
        ai_total = int(dict(snapshot.get("ai") or {}).get("total") or 0)
        ai_needed = active > 0 and (due > 0 or ai_blocked > 0)
        ai_down = operational and ai_needed and healthy == 0
        runtime_started = self._parse_iso(str(snapshot.get("runtime_started_at") or ""))
        runtime_age = max(0.0, now - runtime_started) if runtime_started is not None else 0.0
        hard_ai_down = bool(ai_down and ai_blocked >= 25 and runtime_age >= 30.0)
        elapsed = self._condition_elapsed("AI_DOWN", ai_down, now)
        if ai_down and (hard_ai_down or elapsed >= cfg.ai_grace_seconds):
            providers = ", ".join(f"{p.get('provider')}={p.get('state')}" for p in snapshot.get("providers") or []) or "провайдери ще не дали стан"
            mode = "hard backlog" if hard_ai_down else f"grace {int(elapsed)}s/{cfg.ai_grace_seconds}s"
            incidents.append(Incident(
                "CRITICAL",
                "AI_DOWN",
                "AI pipeline зупинений",
                f"Healthy 0/{ai_total}, WAITING_AI={ai_blocked}, active={active}, due={due}; trigger={mode}. {providers}",
            ))

        last_update_ts = self._parse_iso(str(queue.get("last_job_update") or ""))
        queue_stalled = bool(
            operational and due > 0 and runtime_age >= max(600.0, float(cfg.queue_stall_seconds))
            and last_update_ts is not None and now - last_update_ts >= cfg.queue_stall_seconds
        )
        elapsed = self._condition_elapsed("QUEUE_STALLED", queue_stalled, now)
        if queue_stalled and elapsed >= 0:
            incidents.append(Incident("WARNING", "QUEUE_STALLED", "Черга реально не рухається", f"Due jobs={due}; остання job-активність {queue.get('last_job_update') or 'невідома'}."))

        channel_stats = dict(snapshot.get("channel_stats") or {})
        operational = dict(snapshot.get("operational_states") or {})
        for cid, stats in channel_stats.items():
            name = str(stats.get("name") or cid)
            due_ch = int(stats.get("due_jobs") or 0)
            op = dict(operational.get(str(cid)) or {})
            op_state = str(op.get("state") or "HEALTHY")
            reasons = "; ".join(str(x) for x in (op.get("reasons") or []))
            runtime_state = dict(channels.get(str(cid)) or {})
            ccode = f"CHANNEL_COLLECTOR_DEAD_{cid}"
            collector_dead = bool(operational and runtime_state and not bool(runtime_state.get("collector_alive", True)))
            elapsed_collector = self._condition_elapsed(ccode, collector_dead, now)
            if collector_dead and elapsed_collector >= 120:
                incidents.append(Incident("WARNING", ccode, f"Collector каналу «{name}» не працює", "Processing worker живий, але окремий collector thread не працює."))

            code = f"CHANNEL_QUEUE_STALLED_{cid}"
            ch_stalled = op_state == "STALLED"
            self._condition_elapsed(code, ch_stalled, now)
            if ch_stalled:
                incidents.append(Incident("WARNING", code, f"Черга каналу «{name}» реально не рухається", f"Due jobs={due_ch}; {reasons or 'немає job-активності'}."))

            dcode = f"CHANNEL_THROUGHPUT_DEGRADED_{cid}"
            degraded = bool(operational and op_state == "DEGRADED")
            elapsed_deg = self._condition_elapsed(dcode, degraded, now)
            if degraded and elapsed_deg >= 900:
                incidents.append(Incident(
                    "WARNING", dcode, f"Низька пропускна здатність каналу «{name}»",
                    f"Due jobs={due_ch}; oldest_due_age={int(stats.get('oldest_due_age_seconds') or 0)//60} хв; "
                    f"done/30m={int(stats.get('jobs_done_30m') or 0)}; published/30m={int(stats.get('published_30m') or 0)}. {reasons}"
                ))

            total_sources = int(stats.get("sources_total") or 0)
            source_errors = int(stats.get("recent_source_errors_15m") or 0)
            source_bad = bool(operational and total_sources >= 3 and source_errors >= max(3, (total_sources * 3 + 4) // 5))
            scode = f"SOURCE_MASS_FAILURE_{cid}"
            elapsed_source = self._condition_elapsed(scode, source_bad, now)
            if source_bad and elapsed_source >= 120:
                incidents.append(Incident("WARNING", scode, f"Масові помилки джерел у «{name}»", f"За останні 15 хв помилка у {source_errors}/{total_sources} увімкнених джерел."))

        media = dict(snapshot.get("media") or {})
        media_lost = int(media.get("lost_last_60m") or 0)
        m_elapsed = self._condition_elapsed("MEDIA_LOST_ON_PUBLISH", media_lost > 0, now)
        if media_lost > 0 and m_elapsed >= 0:
            sample = list(media.get("items") or [])[:3]
            detail = "; ".join(f"#{x.get('article_id')} {x.get('published_media_count')}/{x.get('source_media_count')}" for x in sample)
            incidents.append(Incident("WARNING", "MEDIA_LOST_ON_PUBLISH", "Медіа втрачено під час публікації", f"За 60 хв: {media_lost} публікацій з неповним медіа. {detail}"))

        return incidents

    def _handle_incidents(self, snapshot: dict[str, Any], incidents: list[Incident], cfg: SupervisorConfig) -> None:
        codes = {i.code for i in incidents}
        previous = set(self._active_codes)
        new_codes = codes - previous
        recovered = previous - codes
        self._active_codes = codes
        with self._lock:
            self._last_incidents = list(incidents)

        payload = {
            "generated_at": now_iso(),
            "version": V2_VERSION,
            "incidents": [asdict(x) for x in incidents],
            "recovered": sorted(recovered),
            "status_file": str(self.status_path),
            "recent_events_file": str(self.recent_events_path),
        }
        self._atomic_json(self.incident_path, payload)
        self._mirror_file(self.incident_path, "incident.json")

        for inc in incidents:
            if inc.code not in new_codes:
                continue
            bundle = self.create_diagnostic_bundle(inc)
            event(
                "supervisor", "incident detected",
                level=40 if inc.severity == "CRITICAL" else 30,
                code=inc.code, detail=inc.detail, diagnostic_bundle=str(bundle),
            )
        for code in sorted(recovered):
            event("supervisor", "incident recovered", code=code)

    def create_diagnostic_bundle(self, incident: Incident | None = None) -> Path:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        code = incident.code if incident else "MANUAL"
        out = self.root / f"Autopilot_Diagnostic_{stamp}_{code}.zip"
        snapshot = self._last_snapshot or self.build_snapshot()
        incident_json = asdict(incident) if incident else {"severity": "INFO", "code": "MANUAL", "title": "Ручний diagnostic bundle", "detail": ""}
        audit = self._recent_audit_events(200)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr("status.json", json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
            zf.writestr("incident.json", json.dumps(incident_json, ensure_ascii=False, indent=2, default=str))
            zf.writestr("recent_events.json", json.dumps(audit, ensure_ascii=False, indent=2, default=str))
            zf.writestr("diagnostic_report.txt", self._diagnostic_report(snapshot, incident_json))
            for name in ("app", "ingest", "ai", "editorial", "worker", "publish", "migration", "supervisor", "feedback", "learning", "media", "error"):
                path = self.logs_dir / f"{name}.log"
                if path.exists():
                    zf.writestr(f"logs/{name}_tail.log", self._redact_text(self._tail_text(path, 500)))
        self._mirror_file(out, out.name)
        event("supervisor", "diagnostic bundle created", path=str(out), code=code)
        return out

    def _recent_audit_events(self, limit: int) -> list[dict[str, Any]]:
        cap = max(1, int(limit))
        db_events: list[dict[str, Any]] = []
        try:
            with self.store.connect() as con:
                rows = con.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (cap,)).fetchall()
            db_events = [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as exc:
            db_events = [{"stream": "supervisor", "event": "audit_read_error", "detail": str(exc)}]

        log_events = self._recent_log_events(cap)
        combined = db_events + log_events
        combined.sort(key=lambda x: str(x.get("created_at") or x.get("timestamp") or ""), reverse=True)
        return combined[:cap]

    def _recent_log_events(self, limit: int) -> list[dict[str, Any]]:
        streams = ("publish", "media", "worker", "ingest", "ai", "editorial", "supervisor", "error")
        each = max(10, min(80, max(1, int(limit)) // max(1, len(streams)) + 8))
        out: list[dict[str, Any]] = []
        line_re = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+(?P<level>[A-Z]+)\s+(?P<logger>\S+)\s+(?P<rest>.*)$")
        for stream in streams:
            path = self.logs_dir / f"{stream}.log"
            if not path.exists():
                continue
            for line in self._tail_text(path, each).splitlines():
                match = line_re.match(line.strip())
                if not match:
                    continue
                rest = match.group("rest")
                payload: dict[str, Any] = {}
                message = rest
                brace = rest.find("{")
                if brace >= 0:
                    message = rest[:brace].strip()
                    try:
                        parsed = json.loads(rest[brace:])
                        if isinstance(parsed, dict):
                            payload = parsed
                    except Exception:
                        payload = {"raw": rest[brace:][:1200]}
                created = match.group("ts")
                try:
                    dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S,%f").astimezone()
                    created = dt.isoformat(timespec="milliseconds")
                except Exception:
                    pass
                out.append({
                    "created_at": created, "stream": stream, "level": match.group("level"),
                    "event": message[:300], "payload": payload,
                })
        out.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return out[:max(1, int(limit))]

    @staticmethod
    def _tail_text(path: Path, lines: int) -> str:
        try:
            data = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(data[-max(1, int(lines)):]) + "\n"
        except Exception as exc:
            return f"LOG_READ_ERROR: {exc}\n"

    @staticmethod
    def _redact_text(text: str) -> str:
        value = str(text or "")
        value = re.sub(r"\b\d{5,12}:[A-Za-z0-9_-]{20,}\b", "<TELEGRAM_BOT_TOKEN_REDACTED>", value)
        value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]{18,}", "Bearer <REDACTED>", value)
        value = re.sub(r"(?i)(api[_ -]?key|api[_ -]?token|authorization)(\s*[=:]\s*)[^\s,}\]]{12,}", r"\1\2<REDACTED>", value)
        return value

    def _diagnostic_report(self, snapshot: dict[str, Any], incident: dict[str, Any]) -> str:
        q = dict(snapshot.get("queue") or {})
        lines = [
            "UA FREE Telegram Autopilot V2 diagnostic bundle",
            f"Version: {V2_VERSION}",
            f"Generated: {snapshot.get('generated_at')}",
            f"Expected running: {snapshot.get('expected_running')}",
            f"Incident: {incident.get('code')} / {incident.get('severity')}",
            f"Detail: {incident.get('detail')}",
            f"AI: {dict(snapshot.get('ai') or {}).get('healthy', 0)}/{dict(snapshot.get('ai') or {}).get('total', 0)} healthy",
            f"Active jobs: {q.get('active', 0)}; due: {q.get('due', 0)}; blockers: {q.get('blockers', {})}",
            f"Published total: {q.get('published_total', 0)}; today: {q.get('published_today', 0)}; last: {q.get('last_publish') or 'none'}",
            f"Database: {snapshot.get('database')}",
            f"Disk: {snapshot.get('disk')}",
            "",
            "No secrets.key, secrets.secure, API keys, Telegram bot tokens or full SQLite database are included.",
        ]
        return "\n".join(lines) + "\n"

    def _mirror_file(self, source: Path, name: str) -> None:
        cfg = self.config
        raw = cfg.mirror_dir.strip()
        if not raw:
            return
        try:
            target_dir = Path(raw).expanduser()
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / name
            temp = target.with_name(target.name + ".tmp")
            shutil.copy2(source, temp)
            os.replace(temp, target)
        except Exception as exc:
            event("supervisor", "supervisor mirror failed", level=30, path=raw, detail=str(exc)[:800])

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(temp, path)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "snapshot": dict(self._last_snapshot),
                "incidents": [asdict(x) for x in self._last_incidents],
                "expected_running": self._expected_running,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "config": asdict(self._config),
            }
