from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .advanced_supervisor import AdvancedSupervisorService
from .agent_feed import AgentFeed
from .fileio import atomic_copy, atomic_write_json
from .supervisor import SupervisorConfig
from .update_protocol import UpdateProtocol


LIVE_FEED_NAMES = (
    "SUPERVISOR FEED — Autopilot V2 LIVE",
    "SUPERVISOR FEED - Autopilot V2 LIVE",
)


class _ProductionAgentFeed(AgentFeed):
    """Agent feed using unique temp files and lock-tolerant atomic replacement."""

    @staticmethod
    def _atomic(path: Path, value: dict[str, Any]) -> None:
        atomic_write_json(path, value)

    def _mirror(self, path: Path) -> None:
        raw = str(getattr(self.config_getter(), "mirror_dir", "") or "").strip()
        if not raw:
            return
        try:
            root = Path(raw).expanduser()
            root.mkdir(parents=True, exist_ok=True)
            atomic_copy(path, root / path.name)
        except OSError:
            pass


class _ProductionUpdateProtocol(UpdateProtocol):
    """Update status writer hardened for Windows and synced folders."""

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, payload)

    def mirror_status(self, mirror_dir: str) -> None:
        raw = str(mirror_dir or "").strip()
        if not raw:
            return
        root = Path(raw)
        try:
            root.mkdir(parents=True, exist_ok=True)
            for source, name in (
                (self.state_path, "update_status.json"),
                (self.result_path, "update_result.json"),
                (self.ready_path, "update_ready.json"),
            ):
                if source.is_file():
                    atomic_copy(source, root / name)
        except Exception:
            # Remote mirror failure must never take down the local runtime.
            return


class ProductionSupervisorService(AdvancedSupervisorService):
    """Production supervisor with one LIVE feed and Windows-safe status writes."""

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)

        # AdvancedSupervisor constructs these before its worker thread starts.
        # Replace them now so all production writes use the hardened primitives.
        self.update_protocol = _ProductionUpdateProtocol()
        self.agent = _ProductionAgentFeed(
            root=self.root,
            store=self.store,
            config_getter=lambda: self.config,
        )

        live = self._discover_live_mirror_dir()
        if live and str(self.config.mirror_dir or "").strip() != live:
            cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": live}).normalized()
            self.save_config(cfg)
        self._status_sequence = 0

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        atomic_write_json(path, value)

    def _mirror_file(self, source: Path, name: str) -> None:
        raw = self.config.mirror_dir.strip()
        if not raw:
            return
        try:
            target_dir = Path(raw).expanduser()
            target_dir.mkdir(parents=True, exist_ok=True)
            atomic_copy(source, target_dir / name)
            from .storage import now_iso
            self._mirror_last_ok_at = now_iso()
            self._mirror_last_error = ""
        except Exception as exc:
            self._mirror_last_error = f"{type(exc).__name__}: {exc}"[:800]

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
