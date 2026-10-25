from __future__ import annotations

import json
import os
import time
import threading
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
from .outbound_telemetry_233 import BoundedTelemetryPump
from ..secrets_store import load_secrets
from .commercial_profile_audit import audit_commercial_profiles
from .operator_data_snapshot import export_operator_data_snapshot


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

# Canonical Google Drive folder observed by the external supervisor. RC103 used
# name-only lookup, which is ambiguous across My Drive / Shared Drive and duplicate
# folder names. Keep an environment override for portability.
CANONICAL_LIVE_FEED_FOLDER_ID = "1tm0Xdd5V4mDHm7iZza3SnHdEXR2VMa-0"


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
        self.reload_drive_transport()
        # Google Drive and OAuth requests are never run on V2-Supervisor thread.
        # At most one newest pending payload per allowlisted JSON file.
        self._telemetry_pump = BoundedTelemetryPump(self._deliver_telemetry_payload)
        self._operator_snapshot_next_at = time.monotonic() + 600.0
        self._operator_snapshot_running = False
        self._operator_snapshot_status: dict[str, object] = {"status":"scheduled","interval_minutes":60,"redacted":True}

    def reload_drive_transport(self) -> dict[str, object]:
        """Reload operator-visible Drive credentials/folder without restarting runtime."""
        try:
            secrets_cfg = load_secrets()
            saved_folder = str(getattr(secrets_cfg, "google_drive_folder_id", "") or "").strip()
        except Exception:
            saved_folder = ""
        folder_id = str(
            os.environ.get("UA_FREE_AUTOPILOT_LIVE_FOLDER_ID")
            or saved_folder
            or CANONICAL_LIVE_FEED_FOLDER_ID
        ).strip()
        self._drive_api = DirectDriveTelemetry(CANONICAL_LIVE_FEED_NAME, folder_id=folder_id)
        event("supervisor", "Drive telemetry transport reloaded", folder_id=folder_id)
        return self._drive_api.status()

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

            # RC103 migration: old installations still point to
            # ``SUPERVISOR FEED — Autopilot V2``. If its parent Drive directory is
            # mounted, create/use the canonical sibling automatically instead of
            # declaring fallback unavailable.
            try:
                parent = configured_path.parent
                if parent.is_dir():
                    canonical_sibling = parent / CANONICAL_LIVE_FEED_NAME
                    canonical_sibling.mkdir(parents=True, exist_ok=True)
                    cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": str(canonical_sibling)}).normalized()
                    self.save_config(cfg)
                    self._rc55_mirror_targets = [canonical_sibling]
                    self._rc55_mirror_targets_checked_at = now
                    event(
                        "supervisor",
                        "migrated local telemetry fallback to canonical folder",
                        old_mirror=configured,
                        mirror_dir=str(canonical_sibling),
                    )
                    return [canonical_sibling]
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

    def _deliver_telemetry_payload(self, name: str, payload: bytes) -> str:
        """Background-only Drive transport; one canonical local fallback.

        Original source file is used by atomic_copy only if the Google Drive
        Desktop fallback is needed. In that case we deliberately copy the
        *newest* local snapshot instead of resurrecting an older packet.
        """
        try:
            self._drive_api.upload_bytes(name, payload)
            from .storage import now_iso
            self._mirror_last_ok_at = now_iso()
            self._mirror_last_error = ""
            return "google_drive_api"
        except Exception as exc:
            api_error = f"Drive API: {type(exc).__name__}: {exc}"[:500]
            event(
                "supervisor", "Drive API telemetry failed; trying local fallback",
                level=30, file=name, detail=api_error,
            )

        targets = self._rc55_existing_live_targets(force=False)
        if not targets:
            try:
                self.ensure_live_mirror(force=True)
            except Exception:
                pass
            targets = self._rc55_existing_live_targets(force=True)
        for target_dir in targets[:1]:
            try:
                source = self.root / name
                if not self._rc55_valid_telemetry_source(source, name):
                    raise ValueError("source changed or invalid during fallback")
                atomic_copy(source, target_dir / name)
                from .storage import now_iso
                self._mirror_last_ok_at = now_iso()
                self._mirror_last_error = ""
                return "local_fallback"
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"[:500]
                self._mirror_last_error = f"{api_error}; fallback: {local_error}"
                raise RuntimeError(self._mirror_last_error) from exc
        self._mirror_last_error = (
            f"{api_error}; fallback: canonical local Drive folder unavailable"
        )
        raise RuntimeError(self._mirror_last_error)

    def _mirror_file(self, source, name: str) -> None:
        """Queue only an immutable, validated JSON payload; no network here.

        Historical atomic_copy fallback runs via _deliver_telemetry_payload,
        not on the supervisor heartbeat/publishing thread.
        """
        name = str(name or "")
        if name not in _OUTBOUND_TELEMETRY_FILES:
            return
        source = Path(source)
        if not self._rc55_valid_telemetry_source(source, name):
            self._mirror_last_error = f"refused invalid telemetry payload for {name}"
            event(
                "supervisor", "refused invalid telemetry mirror payload",
                level=40, file=name, path=str(source),
            )
            return
        try:
            # Serialize before enqueueing: subsequent supervisor ticks may
            # atomically replace the file before the sender has time to act.
            self._telemetry_pump.submit(name, source.read_bytes())
        except Exception as exc:
            self._mirror_last_error = (
                f"telemetry queue rejected {name}: {type(exc).__name__}: {exc}"
            )[:600]
            event(
                "supervisor", "telemetry queue failed",
                level=40, file=name, detail=self._mirror_last_error,
            )

    def stop(self, timeout: float = 4.0) -> None:
        # No long Google timeout during a deliberate Windows operator stop.
        self._telemetry_pump.stop(timeout=0.2)
        super().stop(timeout=timeout)

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
        try:
            snapshot["commercial_profile_audit"] = audit_commercial_profiles(self.store)
        except Exception as exc:
            snapshot["commercial_profile_audit"] = {"healthy": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
        transport = dict(snapshot.get("transport") or {})
        transport["outbound_pump"] = self._telemetry_pump.status()
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

    def _schedule_operator_snapshot_if_due(self) -> None:
        """Background-only exporter; never delay publishing or fast telemetry."""
        if self._operator_snapshot_running or time.monotonic() < self._operator_snapshot_next_at:
            return
        self._operator_snapshot_running = True
        self._operator_snapshot_next_at = time.monotonic() + 900.0

        def work() -> None:
            try:
                output = self.root / "operator_data_current.sqlite3"
                report = export_operator_data_snapshot(self.store.path, output)
                folder = str(self._drive_api.status().get("configured_folder_id") or CANONICAL_LIVE_FEED_FOLDER_ID)
                drive = DirectDriveTelemetry(CANONICAL_LIVE_FEED_NAME, folder_id=folder)
                file_id = drive.upload_path(output, name="operator_data_current.sqlite3")
                self._operator_snapshot_status = {
                    "status":"uploaded","redacted":True,"file_id":file_id,
                    "size_bytes":report["size_bytes"],"rows":report["rows"],
                    "updated_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"interval_minutes":60
                }
                self._operator_snapshot_next_at = time.monotonic() + 3600.0
                event("supervisor","operator data snapshot uploaded",size_bytes=report["size_bytes"],file_id=file_id)
            except Exception as exc:
                self._operator_snapshot_status = {
                    "status":"error","redacted":True,
                    "detail":f"{type(exc).__name__}: {exc}"[:300],"interval_minutes":60
                }
                event("supervisor","operator data snapshot failed",level=30,detail=str(exc)[:400])
            finally:
                self._operator_snapshot_running = False

        threading.Thread(target=work,name="Autopilot-Operator-Data-Snapshot",daemon=True).start()

    def _loop(self) -> None:
        # Deliberately bypass the inherited remote maintenance tick. This loop only
        # writes local state, evaluates local health, mirrors passive telemetry and
        # invokes the local Telegram reporter. It never consumes remote commands.
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                cfg = self.config
                if cfg.enabled:
                    self._schedule_operator_snapshot_if_due()
                    snapshot = self.write_snapshot()
                    snapshot["operator_data_snapshot"] = dict(self._operator_snapshot_status)
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
