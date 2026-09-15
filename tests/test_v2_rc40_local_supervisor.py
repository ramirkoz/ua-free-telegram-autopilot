from __future__ import annotations

import inspect
from types import SimpleNamespace

from telegram_autopilot.v2.local_reporter import LocalTelegramReporter
from telegram_autopilot.v2.local_supervisor import (
    LocalOnlyProductionSupervisorService,
    _REMOTE_ONLY_INCIDENTS,
)


def test_local_report_is_built_from_local_snapshot_only() -> None:
    snapshot = {
        "version": "2.0.0-rc40",
        "lifecycle_state": "RUNNING",
        "runtime_running": True,
        "live_workers": 3,
        "live_collectors": 3,
        "database": {"ok": True},
        "ai": {"state": "HEALTHY", "healthy": 2, "total": 6, "blocked_jobs": 0},
        "queue": {"active": 7, "due": 2, "published_today": 11},
        "channel_stats": {
            "1": {"published_60m": 1},
            "2": {"published_60m": 2},
        },
    }
    report = LocalTelegramReporter.build_report(snapshot, [])
    assert report["version"] == "2.0.0-rc40"
    assert report["workers_alive"] == 3
    assert report["collectors_alive"] == 3
    assert report["published_60m"] == 3
    assert report["incidents"] == []
    text = LocalTelegramReporter.format_message(report)
    assert "Autopilot · локальний звіт" in text
    assert "workers 3/3" in text


def test_local_only_loop_cannot_execute_remote_agent_feed() -> None:
    source = inspect.getsource(LocalOnlyProductionSupervisorService._loop)
    assert "agent.observe" not in source
    assert "local_reporter.observe" in source


def test_remote_telemetry_incidents_are_explicitly_suppressed() -> None:
    assert "SUPERVISOR_MIRROR_MISSING" in _REMOTE_ONLY_INCIDENTS
    assert "SUPERVISOR_MIRROR_ERROR" in _REMOTE_ONLY_INCIDENTS
    assert "SUPERVISOR_TELEMETRY_STALE" in _REMOTE_ONLY_INCIDENTS


def test_local_reporter_status_declares_no_remote_control(tmp_path) -> None:
    reporter = LocalTelegramReporter(root=tmp_path)
    status = reporter.status()
    assert status["mode"] == "local_only"
    assert status["remote_agent"] is False
    assert status["remote_commands"] is False
