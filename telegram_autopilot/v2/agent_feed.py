from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import V2_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class AgentFeed:
    """Durable local/Drive bridge for remote maintenance and hourly reports.

    It does not execute code and cannot modify the application. It exposes compact
    facts that a remote agent can inspect, and it mirrors an explicit review request
    whenever the supervisor sees a real incident.
    """

    def __init__(self, *, root: Path, store: Any, config_getter) -> None:
        self.root = Path(root) / "agent"
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.config_getter = config_getter
        self.events_path = self.root / "agent_events.jsonl"
        self.hourly_path = self.root / "hourly_latest.json"
        self.journal_path = self.root / "agent_journal_since_review.json"
        self.request_path = self.root / "agent_request.json"
        self.review_path = self.root / "review_ack.json"
        self.state_path = self.root / "state.json"
        self._state = self._read_json(self.state_path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return dict(value) if isinstance(value, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _atomic(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)

    def _mirror(self, path: Path) -> None:
        raw = str(getattr(self.config_getter(), "mirror_dir", "") or "").strip()
        if not raw:
            return
        try:
            root = Path(raw).expanduser()
            root.mkdir(parents=True, exist_ok=True)
            tmp = root / (path.name + ".tmp")
            shutil.copy2(path, tmp)
            os.replace(tmp, root / path.name)
        except OSError:
            pass

    def _metrics(self) -> dict[str, int]:
        with self.store.connect() as con:
            scalar = lambda sql: int(con.execute(sql).fetchone()[0] or 0)
            return {
                "articles": scalar("SELECT COUNT(*) FROM articles"),
                "published": scalar("SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED'"),
                "ready": scalar("SELECT COUNT(*) FROM articles WHERE stage='READY' AND decision='PUBLISH'"),
                "rejected": scalar("SELECT COUNT(*) FROM articles WHERE decision='REJECT'"),
                "active_jobs": scalar("SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','WAITING','LEASED')"),
                "waiting_ai": scalar("SELECT COUNT(*) FROM articles WHERE blocked_by='AI'"),
                "blocked_media": scalar("SELECT COUNT(*) FROM articles WHERE blocked_by='MEDIA'"),
                "source_errors": scalar("SELECT COUNT(*) FROM sources WHERE last_error<>''"),
            }

    @staticmethod
    def _delta(current: dict[str, int], previous: dict[str, Any]) -> dict[str, int]:
        return {key: int(value) - int(previous.get(key) or 0) for key, value in current.items()}

    def _append_event(self, value: dict[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
        try:
            if self.events_path.stat().st_size > 4 * 1024 * 1024:
                lines = self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()[-1500:]
                self.events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass
        self._mirror(self.events_path)

    def _rebuild_journal(self) -> None:
        reviewed = str(self._read_json(self.review_path).get("reviewed_at") or "")
        try:
            lines = self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()[-1000:]
        except OSError:
            lines = []
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict) and (not reviewed or str(item.get("at") or "") > reviewed):
                events.append(item)
        payload = {"generated_at": _now(), "since_review": reviewed or None, "event_count": len(events), "events": events[-500:]}
        self._atomic(self.journal_path, payload)
        self._mirror(self.journal_path)

    def mark_reviewed(self) -> None:
        self._atomic(self.review_path, {"reviewed_at": _now()})
        self._rebuild_journal()

    def observe(self, snapshot: dict[str, Any], incidents: list[Any], update_status: dict[str, Any] | None = None) -> dict[str, Any]:
        now_epoch = time.time()
        metrics = self._metrics()
        previous = dict(self._state.get("last_metrics") or {})
        delta = self._delta(metrics, previous) if previous else {key: 0 for key in metrics}
        codes = [str(getattr(item, "code", "UNKNOWN")) for item in incidents]
        previous_codes = list(self._state.get("last_incidents") or [])
        changed = any(value != 0 for value in delta.values()) or codes != previous_codes
        update_state = str(dict((update_status or {}).get("state") or {}).get("state") or "IDLE")

        if changed or not self._state:
            self._append_event({
                "at": _now(), "kind": "supervisor_change", "version": V2_VERSION,
                "metrics": metrics, "delta": delta, "incidents": codes,
                "update_state": update_state,
                "ui": dict(snapshot.get("ui") or {}),
                "media": dict(snapshot.get("media") or {}),
            })
            self._rebuild_journal()

        if codes:
            request = {
                "generated_at": _now(), "status": "needs_remote_review", "version": V2_VERSION,
                "incidents": codes,
                "instructions": [
                    "read status.json, incident.json, recent_events.json and agent_journal_since_review.json",
                    "diagnose the concrete defect before changing code",
                    "if code changes are needed: branch -> tests -> PR -> CI -> Windows release",
                    "for update, publish only a validated fixed-repository release request/manifest",
                ],
            }
            self._atomic(self.request_path, request)
            self._mirror(self.request_path)
        else:
            try:
                self.request_path.unlink()
            except FileNotFoundError:
                pass
            # A recovered incident must also disappear from the Drive mirror.
            # Leaving an old agent_request.json there makes a remote agent diagnose
            # a problem that has already recovered.
            raw = str(getattr(self.config_getter(), "mirror_dir", "") or "").strip()
            if raw:
                try:
                    (Path(raw).expanduser() / self.request_path.name).unlink(missing_ok=True)
                except OSError:
                    pass

        last_hourly = float(self._state.get("last_hourly_epoch") or 0.0)
        if not last_hourly:
            last_hourly = now_epoch
        if now_epoch - last_hourly >= 3600:
            hourly_prev = dict(self._state.get("hourly_metrics") or metrics)
            report = {
                "generated_at": _now(), "version": V2_VERSION,
                "metrics": metrics, "delta": self._delta(metrics, hourly_prev),
                "incidents": codes, "update_state": update_state,
                "ai": dict(snapshot.get("ai") or {}),
                "queue": dict(snapshot.get("queue") or {}),
                "media": dict(snapshot.get("media") or {}),
                "ui": dict(snapshot.get("ui") or {}),
                "channel_stats": dict(snapshot.get("channel_stats") or {}),
            }
            self._atomic(self.hourly_path, report)
            self._mirror(self.hourly_path)
            self._append_event({"at": _now(), "kind": "hourly_report", **report})
            last_hourly = now_epoch
            self._state["hourly_metrics"] = metrics

        self._state.update({
            "last_metrics": metrics, "last_incidents": codes,
            "last_hourly_epoch": last_hourly, "updated_at": _now(),
        })
        self._atomic(self.state_path, self._state)
        return {"metrics": metrics, "delta": delta, "incidents": codes, "update_state": update_state}
