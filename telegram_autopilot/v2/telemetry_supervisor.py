from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .loghub import event
from .media_supervisor import MediaAwareProductionSupervisorService
from .storage import now_iso
from .supervisor import Incident, SupervisorConfig


class TelemetryProductionSupervisorService(MediaAwareProductionSupervisorService):
    """Self-healing Google Drive telemetry on top of the production supervisor.

    Windows/Drive remounts may leave a perfectly valid local path pointing at the
    wrong/stale mount. RC32 re-discovers the canonical LIVE feed at startup and after
    write failures, retries one mirror write, and exposes transport repair state in
    every snapshot instead of failing silently.
    """

    REDISCOVER_SECONDS = 15.0
    STALE_SECONDS = 90.0

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)
        self._telemetry_last_discovery_epoch = 0.0
        self._telemetry_last_discovery_error = ""
        self._telemetry_last_repair_at = ""
        self._telemetry_repair_count = 0

    @staticmethod
    def _path_stamp(path: Path) -> float:
        try:
            status = path / "status.json"
            return status.stat().st_mtime if status.is_file() else path.stat().st_mtime
        except OSError:
            return 0.0

    def _candidate_mirrors(self) -> list[Path]:
        out: list[Path] = []
        for resolver in (self._discover_live_mirror_dir, self._discover_mirror_dir):
            try:
                raw = str(resolver() or "").strip()
            except Exception as exc:
                self._telemetry_last_discovery_error = f"{type(exc).__name__}: {exc}"[:800]
                continue
            if not raw:
                continue
            path = Path(raw).expanduser()
            try:
                if path.is_dir() and all(str(path) != str(existing) for existing in out):
                    out.append(path)
            except OSError:
                continue
        out.sort(key=self._path_stamp, reverse=True)
        return out

    def ensure_live_mirror(self, *, force: bool = False) -> str:
        now = time.time()
        current_raw = str(self.config.mirror_dir or "").strip()
        current = Path(current_raw).expanduser() if current_raw else None
        current_ok = False
        if current is not None:
            try:
                current_ok = current.is_dir()
            except OSError:
                current_ok = False

        if not force and current_ok and now - self._telemetry_last_discovery_epoch < self.REDISCOVER_SECONDS:
            return str(current)

        self._telemetry_last_discovery_epoch = now
        candidates = self._candidate_mirrors()
        chosen = candidates[0] if candidates else (current if current_ok else None)
        if chosen is None:
            self._telemetry_last_discovery_error = self._telemetry_last_discovery_error or "LIVE supervisor mirror not found"
            return ""

        chosen_raw = str(chosen)
        if chosen_raw != current_raw:
            cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": chosen_raw}).normalized()
            self.save_config(cfg)
            self._telemetry_repair_count += 1
            self._telemetry_last_repair_at = now_iso()
            event(
                "supervisor", "telemetry mirror repaired", level=30,
                previous=current_raw, mirror_dir=chosen_raw, repair_count=self._telemetry_repair_count,
            )
        self._telemetry_last_discovery_error = ""
        return chosen_raw

    def start(self) -> None:
        self.ensure_live_mirror(force=True)
        super().start()

    def _mirror_file(self, source: Path, name: str) -> None:
        raw = self.ensure_live_mirror(force=False)
        if not raw:
            self._mirror_last_error = "LIVE supervisor mirror not found"
            event("supervisor", "supervisor mirror unavailable", level=30, file=name)
            return

        previous_error = self._mirror_last_error
        super()._mirror_file(source, name)
        if not self._mirror_last_error:
            if previous_error:
                event("supervisor", "supervisor mirror recovered", mirror_dir=raw, file=name)
            return

        first_error = self._mirror_last_error
        event(
            "supervisor", "supervisor mirror failed", level=30,
            path=raw, file=name, detail=first_error,
        )
        repaired = self.ensure_live_mirror(force=True)
        if repaired and repaired != raw:
            super()._mirror_file(source, name)
            if not self._mirror_last_error:
                event("supervisor", "supervisor mirror retry succeeded", mirror_dir=repaired, file=name)
                return
        self._mirror_last_error = first_error

    def build_snapshot(self) -> dict[str, Any]:
        self.ensure_live_mirror(force=False)
        snapshot = super().build_snapshot()
        transport = dict(snapshot.get("transport") or {})
        transport.update(
            {
                "telemetry_repair_count": self._telemetry_repair_count,
                "telemetry_last_repair_at": self._telemetry_last_repair_at,
                "telemetry_last_discovery_error": self._telemetry_last_discovery_error,
                "telemetry_self_heal": True,
            }
        )
        snapshot["transport"] = transport
        return snapshot

    @staticmethod
    def _age_seconds(value: str) -> float | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, time.time() - dt.timestamp())
        except Exception:
            return None

    def evaluate(self, snapshot: dict[str, Any], cfg: SupervisorConfig | None = None) -> list[Incident]:
        incidents = list(super().evaluate(snapshot, cfg))
        expected = bool(snapshot.get("expected_running") or snapshot.get("runtime_running"))
        transport = dict(snapshot.get("transport") or {})
        mirror_configured = bool(transport.get("local_mirror_configured"))
        last_ok = str(transport.get("local_mirror_last_ok_at") or "")
        age = self._age_seconds(last_ok)
        stale = bool(expected and mirror_configured and (age is None or age >= self.STALE_SECONDS))
        elapsed = self._condition_elapsed("SUPERVISOR_TELEMETRY_STALE", stale, time.time())
        if stale and elapsed >= 60.0:
            detail = (
                "Google Drive telemetry has no confirmed successful mirror write"
                if age is None
                else f"Google Drive telemetry mirror has been stale for {age:.0f} s"
            )
            incidents.append(
                Incident(
                    "WARNING",
                    "SUPERVISOR_TELEMETRY_STALE",
                    "Віддалена телеметрія не оновлюється",
                    f"{detail}; mirror={self.config.mirror_dir or 'not configured'}; "
                    f"last_error={transport.get('local_mirror_last_error') or self._telemetry_last_discovery_error or 'none'}",
                )
            )
        return incidents

    def summary(self) -> dict[str, Any]:
        value = super().summary()
        value["telemetry"] = {
            "mirror_dir": str(self.config.mirror_dir or ""),
            "last_ok_at": self._mirror_last_ok_at,
            "last_error": self._mirror_last_error,
            "repair_count": self._telemetry_repair_count,
            "last_repair_at": self._telemetry_last_repair_at,
            "last_discovery_error": self._telemetry_last_discovery_error,
        }
        return value
