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
from .production_supervisor import CANONICAL_LIVE_FEED_NAME, LEGACY_LIVE_FEED_NAMES, LIVE_FEED_NAMES, _ProductionUpdateProtocol
from .supervisor import Incident, SupervisorConfig, SupervisorService
from .fileio import atomic_copy
from . import V2_VERSION
from .telemetry_supervisor import TelemetryProductionSupervisorService
from .drive_api_telemetry import DirectDriveTelemetry


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
        # RC64: passive telemetry prefers the Google Drive API. The historical
        # filesystem mirror remains fallback-only for machines where OAuth is
        # intentionally unavailable. Core runtime work never depends on either.
        self._drive_api = DirectDriveTelemetry(CANONICAL_LIVE_FEED_NAME)

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
        """Resolve exactly one telemetry target.

        RC55 fanned status files out to every folder with a matching display name.
        Google Drive permits duplicate folder names, so that made a stale/read-only
        duplicate look alive while the real observer watched a different folder.
        RC63 gives one uniquely named canonical folder absolute priority and keeps a
        single legacy fallback only for migration.
        """
        now = time.monotonic()
        if not force and self._rc55_mirror_targets and now - self._rc55_mirror_targets_checked_at < 60.0:
            return list(self._rc55_mirror_targets)

        configured = str(self.config.mirror_dir or "").strip()
        configured_path = Path(configured).expanduser() if configured else None
        if configured_path is not None:
            try:
                if configured_path.is_dir() and configured_path.name == CANONICAL_LIVE_FEED_NAME:
                    self._rc55_mirror_targets = [configured_path]
                    self._rc55_mirror_targets_checked_at = now
                    return [configured_path]
            except OSError:
                pass

        discovered = str(self._discover_live_mirror_dir() or "").strip()
        if discovered:
            path = Path(discovered).expanduser()
            try:
                if path.is_dir():
                    if str(path) != configured:
                        cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": str(path)}).normalized()
                        self.save_config(cfg)
                    self._rc55_mirror_targets = [path]
                    self._rc55_mirror_targets_checked_at = now
                    return [path]
            except OSError:
                pass

        self._rc55_mirror_targets = []
        self._rc55_mirror_targets_checked_at = now
        return []

    def _mirror_file(self, source, name: str) -> None:
        """Send passive telemetry through Drive API, with local-sync fallback only."""
        name = str(name or "")
        if name not in _OUTBOUND_TELEMETRY_FILES:
            return
        source = Path(source)
        if not self._rc55_valid_telemetry_source(source, name):
            self._mirror_last_error = f"refused invalid telemetry payload for {name}"
            event("supervisor", "refused invalid telemetry mirror payload", level=40, file=name, path=str(source))
            return

        api_error = ""
        try:
            self._drive_api.upload_path(source, name=name)
            from .storage import now_iso
            self._mirror_last_ok_at = now_iso()
            self._mirror_last_error = ""
            return
        except Exception as exc:
            api_error = f"Drive API: {type(exc).__name__}: {exc}"[:1000]
            event("supervisor", "Drive API telemetry failed; trying local fallback", level=30, file=name, detail=api_error)

        # Migration fallback only. This path is deliberately secondary so a missing
        # or stale Google Drive Desktop mount can never make cloud telemetry vanish
        # when OAuth is available.
        targets = self._rc55_existing_live_targets(force=False)
        if not targets:
            try:
                self.ensure_live_mirror(force=True)
            except Exception:
                pass
            targets = self._rc55_existing_live_targets(force=True)
        errors: list[str] = []
        for target_dir in targets[:1]:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                atomic_copy(source, target_dir / name)
                from .storage import now_iso
                self._mirror_last_ok_at = now_iso()
                self._mirror_last_error = ""
                return
            except Exception as exc:
                errors.append(f"{target_dir}: {type(exc).__name__}: {exc}")
        local_error = "; ".join(errors)[:800] if errors else "local Drive Desktop fallback not found"
        self._mirror_last_error = f"{api_error}; fallback: {local_error}"[:1200]

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
        drive_api = self._drive_api.status()
        snapshot["transport"] = {
            **transport,
            "mode": "drive_api_outbound_telemetry_plus_signed_update",
            "drive_api": drive_api,
            "drive_api_last_ok_at": drive_api.get("last_ok_at") or "",
            "drive_api_last_error": drive_api.get("last_error") or "",
            "drive_api_credential_source": drive_api.get("credential_source") or "",
            "feed": transport.get("feed") or CANONICAL_LIVE_FEED_NAME,
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
