from __future__ import annotations

import json
import time
from pathlib import Path

from telegram_autopilot.v2.agent_report_format import format_agent_report
from telegram_autopilot.v2 import updater_helper


def test_structured_agent_report_is_compact_ukrainian_operator_report() -> None:
    message = format_agent_report(
        {
            "status": "warning",
            "version": "2.0.0-rc37",
            "generated_at": "2026-09-15T15:00:00+03:00",
            "runtime": {
                "state": "RUNNING",
                "workers": 3,
                "expected_workers": 3,
                "collectors": 3,
                "expected_collectors": 3,
            },
            "channels": {
                "1": {"name": "CTRL+UA", "state": "HEALTHY"},
                "2": {"name": "ПРОДАНО!", "state": "DEGRADED", "reason": "slow source"},
            },
            "database": {"ok": True, "detail": "ok"},
            "ai": {"healthy": 1, "total": 6, "state": "DEGRADED", "blocked_jobs": 12},
            "queue": {"active": 30, "due": 11, "ready": 4, "blockers": {"AI": 12}},
            "publications": {"today": 24, "hour": 3},
            "detected": ["AI degraded", "slow source"],
            "fixed": "медіа fallback закрито",
            "update": "RC37 встановлено",
            "next_action": "штатний контроль",
        }
    )
    assert message.startswith("Autopilot · Перевірка агента\n")
    assert "Статус: ПОПЕРЕДЖЕННЯ" in message
    assert "Runtime: RUNNING · workers 3/3 · collectors 3/3" in message
    assert "Канали: CTRL+UA: HEALTHY; ПРОДАНО!: DEGRADED (slow source)" in message
    assert "База: OK" in message
    assert "AI: 1/6 healthy · DEGRADED · blocked 12" in message
    assert "Виявлено: AI degraded; slow source" in message
    assert len(message) <= 3900


def test_parent_shutdown_escalates_to_exact_pid_kill(monkeypatch) -> None:
    waits = iter([False, True])
    killed: list[int] = []
    monkeypatch.setattr(updater_helper, "_wait_pid_gone", lambda _pid, _timeout: next(waits))
    monkeypatch.setattr(updater_helper, "_kill_pid_only", lambda pid: killed.append(pid))
    assert updater_helper._ensure_parent_stopped(12345) is True
    assert killed == [12345]


def _write_status(root: Path, payload: dict) -> float:
    supervisor = root / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    path = supervisor / "status.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    return now


def test_update_health_gate_requires_fresh_matching_running_supervisor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater_helper, "data_dir", lambda: tmp_path)
    launched = _write_status(
        tmp_path,
        {
            "version": "2.0.0-rc38",
            "database": {"ok": True, "detail": "ok"},
            "enabled_channels": {"1": "A", "2": "B", "3": "C"},
            "expected_running": True,
            "runtime_running": True,
            "lifecycle_state": "RUNNING",
            "live_workers": 3,
            "live_collectors": 3,
        },
    )
    ok, detail = updater_helper._fresh_supervisor_healthy("2.0.0-rc38", launched)
    assert ok is True
    assert "workers=3/3" in detail and "DB=OK" in detail


def test_update_health_gate_rejects_wrong_version_bad_db_or_missing_workers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater_helper, "data_dir", lambda: tmp_path)
    base = {
        "version": "2.0.0-rc38",
        "database": {"ok": True},
        "enabled_channels": {"1": "A", "2": "B", "3": "C"},
        "expected_running": True,
        "runtime_running": True,
        "lifecycle_state": "RUNNING",
        "live_workers": 3,
        "live_collectors": 3,
    }

    launched = _write_status(tmp_path, base)
    assert updater_helper._fresh_supervisor_healthy("2.0.0-rc39", launched)[0] is False

    broken_db = dict(base)
    broken_db["database"] = {"ok": False, "detail": "corrupt"}
    launched = _write_status(tmp_path, broken_db)
    assert updater_helper._fresh_supervisor_healthy("2.0.0-rc38", launched)[0] is False

    short = dict(base)
    short["live_workers"] = 2
    launched = _write_status(tmp_path, short)
    ok, detail = updater_helper._fresh_supervisor_healthy("2.0.0-rc38", launched)
    assert ok is False
    assert "workers=2/3" in detail


def test_update_health_gate_allows_clean_install_with_no_enabled_channels(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater_helper, "data_dir", lambda: tmp_path)
    launched = _write_status(
        tmp_path,
        {
            "version": "2.0.0-rc38",
            "database": {"ok": True},
            "enabled_channels": {},
            "runtime_running": False,
            "live_workers": 0,
            "live_collectors": 0,
        },
    )
    ok, detail = updater_helper._fresh_supervisor_healthy("2.0.0-rc38", launched)
    assert ok is True
    assert "no enabled channels" in detail
