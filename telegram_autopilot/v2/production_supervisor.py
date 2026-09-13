from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .advanced_supervisor import AdvancedSupervisorService
from .supervisor import SupervisorConfig


LIVE_FEED_NAMES = (
    "SUPERVISOR FEED — Autopilot V2 LIVE",
    "SUPERVISOR FEED - Autopilot V2 LIVE",
)


class ProductionSupervisorService(AdvancedSupervisorService):
    """RC22 supervisor with one unambiguous Google Drive transport target.

    RC21 could keep writing to a locally-existing stale duplicate folder and report
    mirror success even though the cloud-visible folder was different. RC22 uses a
    uniquely named LIVE feed and records transport state separately from runtime
    health. The filesystem write remains atomic; the remote agent proves cloud
    visibility by seeing the same monotonically increasing status sequence.
    """

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)
        live = self._discover_live_mirror_dir()
        if live and str(self.config.mirror_dir or "").strip() != live:
            cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": live}).normalized()
            self.save_config(cfg)
        self._status_sequence = 0

    @staticmethod
    def _discover_live_mirror_dir() -> str:
        env = str(os.environ.get("AUTOPILOT_SUPERVISOR_MIRROR") or "").strip()
        if env:
            path = Path(env).expanduser()
            if path.is_dir() and path.name in LIVE_FEED_NAMES:
                return str(path)

        home = Path.home()
        roots = [home, home / "Google Drive", home / "GoogleDrive"]
        if os.name == "nt":
            roots.extend(Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ")

        candidates: list[Path] = []
        for root in roots:
            try:
                if not root.exists():
                    continue
            except OSError:
                continue
            for drive_root in (root, root / "My Drive", root / "Мій диск"):
                for name in LIVE_FEED_NAMES:
                    candidates.append(drive_root / name)

        existing: list[Path] = []
        for path in candidates:
            try:
                if path.is_dir():
                    existing.append(path)
            except OSError:
                pass
        if not existing:
            return ""
        existing.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
        return str(existing[0])

    def build_snapshot(self) -> dict[str, Any]:
        snapshot = super().build_snapshot()
        runtime_running = bool(snapshot.get("runtime_running"))
        stop_requested = bool(snapshot.get("runtime_stop_requested"))
        live_threads = int(snapshot.get("live_workers") or 0) + int(snapshot.get("live_collectors") or 0)

        # Never report the impossible RC21 combination "expected=false but healthy
        # runtime still running" unless a stop was actually requested. This also
        # survives UI callback races because runtime state is authoritative.
        if runtime_running and live_threads > 0 and not stop_requested:
            snapshot["expected_running"] = True
            lifecycle = "RUNNING"
        elif stop_requested and live_threads > 0:
            lifecycle = "STOPPING"
        elif live_threads <= 0:
            lifecycle = "STOPPED"
        else:
            lifecycle = "STARTING"
        snapshot["lifecycle_state"] = lifecycle

        self._status_sequence += 1
        snapshot["transport"] = {
            "feed": "SUPERVISOR FEED — Autopilot V2 LIVE",
            "sequence": self._status_sequence,
            "local_mirror_configured": bool(str(self.config.mirror_dir or "").strip()),
            "local_mirror_last_ok_at": self._mirror_last_ok_at,
            "local_mirror_last_error": self._mirror_last_error,
        }
        return snapshot
