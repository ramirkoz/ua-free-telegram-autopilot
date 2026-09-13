from __future__ import annotations

import json
import os
import shutil
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .agent_feed import AgentFeed
from .loghub import event
from .storage import now_iso
from .supervisor import Incident, SupervisorConfig, SupervisorService
from .update_protocol import UpdateProtocol


class AdvancedSupervisorService(SupervisorService):
    """RC21 KONTUR-style durable supervisor + agent bridge."""

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)
        self.history_path = self.root / "history.jsonl"
        self.state_path = self.root / "state.json"
        self._mirror_last_ok_at = ""
        self._mirror_last_error = ""
        self._load_persistent_state()
        configured = str(self.config.mirror_dir or "").strip()
        if not configured or not Path(configured).expanduser().is_dir():
            found = self._discover_mirror_dir()
            if found:
                cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": found}).normalized()
                self.save_config(cfg)
        self.update_protocol = UpdateProtocol()
        self.agent = AgentFeed(root=self.root, store=self.store, config_getter=lambda: self.config)
        # Base RC19 synchronously built a full SQLite/media/log snapshot from
        # set_expected_running(), which is called by Tk Start/Stop callbacks. Keep
        # the wakeup primitive entirely in the advanced service so RC21 does not
        # need to mutate the large base supervisor module.
        self._poke = threading.Event()

    def set_expected_running(self, value: bool) -> None:
        with self._lock:
            self._expected_running = bool(value)
        self._poke.set()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._poke.clear()
            self._thread = threading.Thread(target=self._loop, name="V2-Supervisor", daemon=True)
            self._thread.start()
        event("supervisor", "advanced supervisor service started")

    def stop(self, timeout: float = 4.0) -> None:
        self._stop.set()
        self._poke.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(max(0.2, float(timeout)))
        event("supervisor", "advanced supervisor service stopped")

    @staticmethod
    def _discover_mirror_dir() -> str:
        env = str(os.environ.get("AUTOPILOT_SUPERVISOR_MIRROR") or "").strip()
        if env and Path(env).expanduser().is_dir():
            return str(Path(env).expanduser())

        feed_names = ("SUPERVISOR FEED — Autopilot V2", "SUPERVISOR FEED - Autopilot V2")
        vault_names = (
            "Project Vault",
            "UA FREE Telegram Autopilot — Project Vault",
            "UA FREE Telegram Autopilot - Project Vault",
        )
        home = Path.home()
        roots: list[Path] = [
            home,
            home / "Google Drive",
            home / "GoogleDrive",
        ]
        if os.name == "nt":
            # Google Drive for Desktop normally exposes My Drive as a mounted drive
            # (often G:), but the letter is configurable. Search every plausible
            # letter instead of assuming D:..K:.
            roots.extend(Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ")

        candidates: dict[str, Path] = {}
        for root in roots:
            try:
                if not root.exists():
                    continue
            except OSError:
                continue
            drive_roots = [root]
            for my_drive in ("My Drive", "Мій диск"):
                drive_roots.append(root / my_drive)
            for drive_root in drive_roots:
                for feed in feed_names:
                    candidates[str(drive_root / feed)] = drive_root / feed
                for vault in vault_names:
                    for feed in feed_names:
                        candidates[str(drive_root / vault / feed)] = drive_root / vault / feed

        def score(path: Path) -> tuple[int, float]:
            try:
                if not path.is_dir():
                    return (-1, 0.0)
                points = 1
                for name, weight in (
                    ("status.json", 120),
                    ("incident.json", 40),
                    ("agent_journal_since_review.json", 35),
                    ("agent_events.jsonl", 25),
                    ("update_status.json", 15),
                ):
                    if (path / name).is_file():
                        points += weight
                if (path / "AGENT_REPORTS").is_dir():
                    points += 20
                stamp = 0.0
                status = path / "status.json"
                if status.is_file():
                    stamp = status.stat().st_mtime
                else:
                    stamp = path.stat().st_mtime
                return (points, stamp)
            except OSError:
                return (-1, 0.0)

        ranked = sorted(((score(path), path) for path in candidates.values()), key=lambda item: item[0], reverse=True)
        if ranked and ranked[0][0][0] >= 1:
            return str(ranked[0][1])
        return ""

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                cfg = self.config
                if cfg.enabled:
                    snapshot = self.write_snapshot()
                    incidents = self.evaluate(snapshot, cfg)
                    self._handle_incidents(snapshot, incidents, cfg)
                    try:
                        self.agent.observe(snapshot, incidents, self.update_protocol.status())
                    except Exception as exc:
                        event("supervisor", "agent feed tick failed", level=30, detail=str(exc)[:800])
            except Exception as exc:
                event("supervisor", "supervisor tick failed", level=40, detail=str(exc)[:1200])
            elapsed = time.monotonic() - started
            delay = max(0.25, float(self.config.interval_seconds) - elapsed)
            self._poke.wait(delay)
            self._poke.clear()

    def _ui_status(self) -> dict[str, Any]:
        stamp = str(getattr(self.runtime, "ui_heartbeat_at", "") or "")
        parsed = self._parse_iso(stamp)
        age = max(0.0, time.time() - parsed) if parsed is not None else 0.0
        return {
            "heartbeat_at": stamp,
            "heartbeat_age_seconds": round(age, 2),
            "refresh_inflight": bool(getattr(self.runtime, "ui_refresh_inflight", False)),
            "last_refresh_ms": int(getattr(self.runtime, "ui_last_refresh_ms", 0) or 0),
        }

    def build_snapshot(self) -> dict[str, Any]:
        value = super().build_snapshot()
        value["ui"] = self._ui_status()
        value["update"] = self.update_protocol.status()
        value["mirror"] = {
            "configured": bool(self.config.mirror_dir.strip()),
            "path": self.config.mirror_dir.strip(),
            "last_ok_at": self._mirror_last_ok_at,
            "last_error": self._mirror_last_error,
        }
        return value

    def write_snapshot(self) -> dict[str, Any]:
        snapshot = super().write_snapshot()
        self._append_history(snapshot)
        return snapshot

    def evaluate(self, snapshot: dict[str, Any], cfg: SupervisorConfig | None = None) -> list[Incident]:
        incidents = list(super().evaluate(snapshot, cfg))
        now = time.time()
        expected = bool(snapshot.get("expected_running"))
        mirror = dict(snapshot.get("mirror") or {})
        missing = bool(expected and not mirror.get("configured"))
        elapsed = self._condition_elapsed("SUPERVISOR_MIRROR_MISSING", missing, now)
        if missing and elapsed >= 60.0:
            incidents.append(Incident(
                "WARNING", "SUPERVISOR_MIRROR_MISSING", "Google Drive feed не налаштований",
                "Наглядач працює локально, але віддалений агент не бачить status/incident/report файли.",
            ))
        if expected and str(mirror.get("last_error") or ""):
            incidents.append(Incident(
                "WARNING", "SUPERVISOR_MIRROR_ERROR", "Помилка запису Google Drive feed", str(mirror.get("last_error"))[:800],
            ))
        ui = dict(snapshot.get("ui") or {})
        lag = float(ui.get("heartbeat_age_seconds") or 0.0)
        stalled = bool(expected and ui.get("heartbeat_at") and lag >= 5.0)
        elapsed = self._condition_elapsed("UI_STALLED", stalled, now)
        if stalled and elapsed >= 2.0:
            incidents.append(Incident(
                "WARNING", "UI_STALLED", "Інтерфейс не відповідає",
                f"Tk heartbeat не оновлювався {lag:.1f} с; backend контролюється окремо.",
            ))
        return incidents

    def _handle_incidents(self, snapshot: dict[str, Any], incidents: list[Incident], cfg: SupervisorConfig) -> None:
        super()._handle_incidents(snapshot, incidents, cfg)
        self._save_persistent_state()

    def _mirror_file(self, source: Path, name: str) -> None:
        raw = self.config.mirror_dir.strip()
        if not raw:
            return
        try:
            target_dir = Path(raw).expanduser()
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / name
            tmp = target.with_name(target.name + ".tmp")
            shutil.copy2(source, tmp)
            os.replace(tmp, target)
            self._mirror_last_ok_at = now_iso()
            self._mirror_last_error = ""
        except Exception as exc:
            self._mirror_last_error = f"{type(exc).__name__}: {exc}"[:800]
            event("supervisor", "supervisor mirror failed", level=30, path=raw, detail=str(exc)[:800])

    def _append_history(self, snapshot: dict[str, Any]) -> None:
        try:
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
            if self.history_path.stat().st_size > 8 * 1024 * 1024:
                data = self.history_path.read_bytes()[-4 * 1024 * 1024:]
                pos = data.find(b"\n")
                if pos >= 0:
                    data = data[pos + 1:]
                self.history_path.write_bytes(data)
        except OSError:
            pass

    def _load_persistent_state(self) -> None:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(value, dict):
            self._active_codes = {str(x) for x in value.get("active_codes", [])}

    def _save_persistent_state(self) -> None:
        self._atomic_json(self.state_path, {"active_codes": sorted(self._active_codes), "updated_at": now_iso()})

    def summary(self) -> dict[str, Any]:
        value = super().summary()
        value["agent"] = {
            "journal": str(self.agent.journal_path), "hourly": str(self.agent.hourly_path), "request": str(self.agent.request_path),
        }
        value["update"] = self.update_protocol.status()
        return value
