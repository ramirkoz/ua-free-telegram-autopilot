from __future__ import annotations

import time
from typing import Any

from .local_reporter import LocalTelegramReporter
from .loghub import event
from .supervisor import Incident, SupervisorConfig, SupervisorService
from .telemetry_supervisor import TelemetryProductionSupervisorService


_REMOTE_ONLY_INCIDENTS = {
    "SUPERVISOR_MIRROR_MISSING",
    "SUPERVISOR_MIRROR_ERROR",
    "SUPERVISOR_TELEMETRY_STALE",
}


class LocalOnlyProductionSupervisorService(TelemetryProductionSupervisorService):
    """KONTUR-style local-only supervisor.

    Keep local health checks, media/runtime diagnostics, local Telegram status and
    the signed updater channel. Disable the remote maintenance AgentFeed, remote
    review requests, agent journals/hourly feeds, agent Telegram bridge and passive
    Drive status/incident publishing.
    """

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)
        # The inherited constructor creates the historical feed object. It performs
        # no work unless called by the inherited tick; clear the reference so RC40
        # cannot accidentally revive the remote maintenance path.
        self.agent = None
        self.local_reporter = LocalTelegramReporter(root=self.root)
        self._local_report_result: dict[str, Any] = {"status": "starting"}

    def _mirror_file(self, source, name: str) -> None:
        # The LIVE folder remains discoverable/configured for the narrow signed
        # updater protocol. Supervisor status, incidents and agent artefacts are
        # local-only from RC40 onward.
        return

    def build_snapshot(self) -> dict[str, Any]:
        snapshot = super().build_snapshot()
        snapshot.pop("mirror", None)
        snapshot["supervision"] = {
            "mode": "local_only",
            "remote_agent": False,
            "remote_commands": False,
            "remote_agent_telegram_bridge": False,
            "drive_status_mirror": False,
            "signed_updater": True,
            "telegram": self.local_reporter.status(),
        }
        snapshot["local_telegram_report"] = dict(self._local_report_result)
        transport = dict(snapshot.get("transport") or {})
        snapshot["transport"] = {
            "mode": "update_only",
            "feed": transport.get("feed") or "SUPERVISOR FEED — Autopilot V2 LIVE",
            "update_channel_configured": bool(str(self.config.mirror_dir or "").strip()),
            "status_mirror": False,
        }
        return snapshot

    def evaluate(self, snapshot: dict[str, Any], cfg: SupervisorConfig | None = None) -> list[Incident]:
        # Reuse all runtime/database/AI/queue/media checks, but remote telemetry
        # health is intentionally irrelevant in local-only mode.
        return [
            incident
            for incident in super().evaluate(snapshot, cfg)
            if str(incident.code) not in _REMOTE_ONLY_INCIDENTS
        ]

    def _loop(self) -> None:
        # Deliberately bypass the inherited remote maintenance tick. This loop only
        # writes local state, evaluates local health and invokes the local reporter.
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

                    snapshot["local_telegram_report"] = dict(self._local_report_result)
                    snapshot["supervision"]["telegram"] = self.local_reporter.status()
                    self._atomic_json(self.status_path, snapshot)
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
            "mode": "local_only",
            "remote_agent": False,
            "remote_commands": False,
            "remote_agent_telegram_bridge": False,
            "drive_status_mirror": False,
            "signed_updater": True,
            "telegram": self.local_reporter.status(),
        }
        value["update"] = self.update_protocol.status()
        return value
