from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from .advanced_supervisor import AdvancedSupervisorService
from .local_reporter import LocalTelegramReporter
from .loghub import event
from .production_supervisor import _ProductionUpdateProtocol
from .supervisor import Incident, SupervisorConfig, SupervisorService
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

        # Fields normally initialised by TelemetryProductionSupervisorService.
        self._telemetry_last_discovery_epoch = 0.0
        self._telemetry_last_discovery_error = ""
        self._telemetry_last_repair_at = ""
        self._telemetry_repair_count = 0

        self.local_reporter = LocalTelegramReporter(root=self.root)
        self._local_report_result: dict[str, Any] = {"status": "starting"}

    def _mirror_file(self, source, name: str) -> None:
        """Mirror only passive telemetry; never mirror agent/control artefacts."""
        if str(name or "") not in _OUTBOUND_TELEMETRY_FILES:
            return
        TelemetryProductionSupervisorService._mirror_file(self, source, name)

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
