from __future__ import annotations

import json
import os
import time
from pathlib import Path
from dataclasses import asdict
from typing import Any

from .advanced_supervisor import AdvancedSupervisorService
from .local_reporter import LocalTelegramReporter
from .loghub import event
from .production_supervisor import LIVE_FEED_NAMES, _ProductionUpdateProtocol
from .supervisor import Incident, SupervisorConfig, SupervisorService
from .fileio import atomic_copy
from . import V2_VERSION
from .telemetry_supervisor import TelemetryProductionSupervisorService


# Passive observability only. These files are written from the application to the
# synced LIVE folder and are never treated as commands. Agent/review/journal files
# are intentionally absent from this allowlist.
_OUTBOUND_TELEMETRY_FILES = frozenset({
    "status.json",
    "recent_events.json",
    "incident.json",
})

# Kept as a compatibility hook for tests/callers from RC40-RC42. Once passive
# telemetry is restored these transport incidents are useful again, so nothing is
# suppressed here.
_REMOTE_ONLY_INCIDENTS: frozenset[str] = frozenset()


class LocalOnlyProductionSupervisorService(TelemetryProductionSupervisorService):
    """Local supervisor with outbound-only observability and no remote agent.

    Keep local health checks, media/runtime diagnostics, local Telegram reporting,
    passive status/event/incident mirroring and the signed updater channel. The
    remote maintenance AgentFeed is never constructed, so review requests, agent
    journals/hourly feeds, remote commands and the agent Telegram bridge cannot run.
    """

    REMOTE_AGENT_ENABLED = False

    def __init__(self, store, runtime, logs_dir):
        # Intentionally bypass ProductionSupervisorService.__init__ because that
        # historical constructor creates _ProductionAgentFeed. AdvancedSupervisor
        # honours REMOTE_AGENT_ENABLED=False and therefore creates no AgentFeed.
        AdvancedSupervisorService.__init__(self, store, runtime, logs_dir)
        self.update_protocol = _ProductionUpdateProtocol()

        live = self._discover_live_mirror_dir()
        if live and str(self.config.mirror_dir or "").strip() != live:
            cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": live}).normalized()
            self.save_config(cfg)
        self._status_sequence = 0
        self._rc55_mirror_targets: list[Path] = []
        self._rc55_mirror_targets_checked_at = 0.0

        # Fields normally initialised by TelemetryProductionSupervisorService.
        self._telemetry_last_discovery_epoch = 0.0
        self._telemetry_last_discovery_error = ""
        self._telemetry_last_repair_at = ""
        self._telemetry_repair_count = 0

        self.local_reporter = LocalTelegramReporter(root=self.root)
        self._local_report_result: dict[str, Any] = {"status": "starting"}

    @staticmethod
    def _rc55_valid_telemetry_source(source: Path, name: str) -> bool:
        """Never mirror arbitrary/corrupted JSON into passive telemetry slots."""
        if name not in _OUTBOUND_TELEMETRY_FILES:
            return False
        try:
            value = json.loads(Path(source).read_text(encoding="utf-8"))
        except Exception:
            return False
        if not isinstance(value, dict):
            return False
        if name == "status.json":
            return value.get("schema") == "ua-free-autopilot-supervisor-v2" and str(value.get("version") or "") == V2_VERSION
        if name == "recent_events.json":
            return str(value.get("version") or "") == V2_VERSION and isinstance(value.get("events"), list)
        if name == "incident.json":
            return str(value.get("version") or "") == V2_VERSION and isinstance(value.get("incidents"), list)
        return False

    def _rc55_existing_live_targets(self, *, force: bool = False) -> list[Path]:
        """Return every existing local Drive LIVE folder, not just one winner.

        Duplicate Drive folders/mounts happened in production. Passive telemetry is
        safe to fan out, and doing so prevents one stale duplicate from making the
        remote observer blind while another mount is actually being synced.
        """
        now = time.monotonic()
        if not force and self._rc55_mirror_targets and now - self._rc55_mirror_targets_checked_at < 300.0:
            return list(self._rc55_mirror_targets)
        candidates: list[Path] = []
        configured = str(self.config.mirror_dir or "").strip()
        if configured:
            candidates.append(Path(configured).expanduser())
        home = Path.home()
        roots = [home, home / "Google Drive", home / "GoogleDrive"]
        if os.name == "nt":
            roots.extend(Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ")
        vault_names = (
            "UA FREE Telegram Autopilot — Project Vault",
            "UA FREE Telegram Autopilot - Project Vault",
            "Project Vault",
        )
        for root in roots:
            try:
                if not root.exists():
                    continue
            except OSError:
                continue
            for drive_root in (root, root / "My Drive", root / "Мій диск"):
                for feed in LIVE_FEED_NAMES:
                    candidates.append(drive_root / feed)
                    for vault in vault_names:
                        candidates.append(drive_root / vault / feed)
        out: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = os.path.normcase(os.path.abspath(str(path)))
            if key in seen:
                continue
            seen.add(key)
            try:
                if path.is_dir():
                    out.append(path)
                    continue
                # A configured LIVE path may have been removed/corrupted by a sync
                # conflict. Re-create it only when its parent is already mounted.
                if configured and key == os.path.normcase(os.path.abspath(configured)) and path.parent.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                    out.append(path)
            except OSError:
                continue
        self._rc55_mirror_targets = out
        self._rc55_mirror_targets_checked_at = now
        return list(out)

    def _mirror_file(self, source, name: str) -> None:
        """Mirror passive telemetry to all known LIVE mounts with schema guard."""
        name = str(name or "")
        if name not in _OUTBOUND_TELEMETRY_FILES:
            return
        source = Path(source)
        if not self._rc55_valid_telemetry_source(source, name):
            self._mirror_last_error = f"refused invalid telemetry payload for {name}"
            event("supervisor", "refused invalid telemetry mirror payload", level=40, file=name, path=str(source))
            return
        targets = self._rc55_existing_live_targets(force=False)
        if not targets:
            # Retain inherited self-healing discovery as a fallback, then rescan.
            try:
                self.ensure_live_mirror(force=True)
            except Exception:
                pass
            targets = self._rc55_existing_live_targets(force=True)
        if not targets:
            self._mirror_last_error = "LIVE supervisor mirror not found"
            return
        errors: list[str] = []
        successes = 0
        for target_dir in targets:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                atomic_copy(source, target_dir / name)
                successes += 1
            except Exception as exc:
                errors.append(f"{target_dir}: {type(exc).__name__}: {exc}")
        if successes:
            from .storage import now_iso
            self._mirror_last_ok_at = now_iso()
            self._mirror_last_error = ""
        else:
            self._mirror_last_error = "; ".join(errors)[:1200]
            self._rc55_existing_live_targets(force=True)

    def build_snapshot(self) -> dict[str, Any]:
        snapshot = super().build_snapshot()
        snapshot["supervision"] = {
            "mode": "local_with_outbound_telemetry",
            "remote_agent": False,
            "agent_object_constructed": False,
            "remote_commands": False,
            "remote_agent_telegram_bridge": False,
            "outbound_telemetry": True,
            "telemetry_direction": "outbound_only",
            "telemetry_files": sorted(_OUTBOUND_TELEMETRY_FILES),
            "signed_updater": True,
            "inbound_control": "signed_update_only",
            "telegram": self.local_reporter.status(),
        }
        snapshot["local_telegram_report"] = dict(self._local_report_result)
        transport = dict(snapshot.get("transport") or {})
        snapshot["transport"] = {
            **transport,
            "mode": "outbound_telemetry_plus_signed_update",
            "feed": transport.get("feed") or "SUPERVISOR FEED — Autopilot V2 LIVE",
            "update_channel_configured": bool(str(self.config.mirror_dir or "").strip()),
            "status_mirror": True,
            "recent_events_mirror": True,
            "incident_mirror": True,
            "remote_commands": False,
        }
        return snapshot

    def evaluate(self, snapshot: dict[str, Any], cfg: SupervisorConfig | None = None) -> list[Incident]:
        # Runtime/database/AI/queue/media and passive telemetry health all matter.
        # There is no agent-specific incident path because AgentFeed is absent.
        return [
            incident
            for incident in super().evaluate(snapshot, cfg)
            if str(incident.code) not in _REMOTE_ONLY_INCIDENTS
        ]

    def _loop(self) -> None:
        # Deliberately bypass the inherited remote maintenance tick. This loop only
        # writes local state, evaluates local health, mirrors passive telemetry and
        # invokes the local Telegram reporter. It never consumes remote commands.
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                cfg = self.config
                if cfg.enabled:
                    snapshot = self.write_snapshot()
                    incidents = self.evaluate(snapshot, cfg)
                    self._handle_incidents(snapshot, incidents, cfg)
                    try:
                        self._local_report_result = self.local_reporter.observe(snapshot, incidents)
                    except Exception as exc:
                        self._local_report_result = {
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}"[:500],
                        }
                        event("supervisor", "local Telegram report failed", level=30, detail=str(exc)[:800])

                    # Re-write and re-mirror the final snapshot so the outbound copy
                    # includes the result of this same tick's local Telegram report.
                    snapshot["local_telegram_report"] = dict(self._local_report_result)
                    snapshot["supervision"]["telegram"] = self.local_reporter.status()
                    self._atomic_json(self.status_path, snapshot)
                    self._mirror_file(self.status_path, "status.json")
                    with self._lock:
                        self._last_snapshot = dict(snapshot)
            except Exception as exc:
                event("supervisor", "local-only supervisor tick failed", level=40, detail=str(exc)[:1200])
            elapsed = time.monotonic() - started
            self._poke.wait(max(0.25, float(self.config.interval_seconds) - elapsed))
            self._poke.clear()

    def summary(self) -> dict[str, Any]:
        value = SupervisorService.summary(self)
        value["supervision"] = {
            "mode": "local_with_outbound_telemetry",
            "remote_agent": False,
            "agent_object_constructed": False,
            "remote_commands": False,
            "remote_agent_telegram_bridge": False,
            "outbound_telemetry": True,
            "telemetry_direction": "outbound_only",
            "telemetry_files": sorted(_OUTBOUND_TELEMETRY_FILES),
            "signed_updater": True,
            "inbound_control": "signed_update_only",
            "telegram": self.local_reporter.status(),
        }
        value["update"] = self.update_protocol.status()
        return value
