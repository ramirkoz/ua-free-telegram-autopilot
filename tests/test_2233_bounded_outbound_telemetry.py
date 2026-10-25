"""2.2.33: bounded outbound telemetry, no Drive calls on supervisor tick."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from telegram_autopilot.v2 import V2_VERSION
from telegram_autopilot.v2.local_supervisor import (
    LocalOnlyProductionSupervisorService,
    _OUTBOUND_TELEMETRY_FILES,
)
from telegram_autopilot.v2.outbound_telemetry_233 import (
    BoundedTelemetryPump,
    TELEMETRY_NAMES,
)


def _until(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def test_queue_accepts_only_passive_telemetry_and_limits_memory():
    entered = threading.Event()
    leave = threading.Event()
    emitted = []

    def send(name, data):
        entered.set()
        leave.wait(2.0)
        emitted.append((name, data))
        return "google_drive_api"

    pump = BoundedTelemetryPump(send)
    try:
        pump.submit("status.json", b"start")
        assert entered.wait(1.0)
        for i in range(1000):
            pump.submit("status.json", f"{i}".encode())
        pump.submit("incident.json", b"one incident")
        pump.submit("recent_events.json", b"recent")
        assert pump.status()["pending_count"] == 3
        assert pump.status()["thread_alive"] is True
        assert pump.status()["remote_control"] is False
        with pytest.raises(ValueError):
            pump.submit("command.json", b"anything")
        leave.set()
        assert _until(lambda: pump.status()["pending_count"] == 0)
        assert ("status.json", b"999") in emitted
        assert len(emitted) <= 4
    finally:
        leave.set()
        pump.stop()


def test_network_failure_retries_without_waiting_on_submitter():
    calls = []
    recovering = threading.Event()

    def send(name, data):
        calls.append((name, data))
        if name == "status.json" and not recovering.is_set():
            raise OSError("Drive temporarily unavailable")
        return "google_drive_api"

    pump = BoundedTelemetryPump(send, retry_seconds=.03, max_retry_seconds=.1)
    try:
        t0 = time.monotonic()
        pump.submit("status.json", b"old")
        assert time.monotonic() - t0 < .1
        assert _until(lambda: bool(pump.status()["last_error"].get("status.json")))
        pump.submit("status.json", b"new")
        pump.submit("incident.json", b"safe")
        assert _until(lambda: pump.status()["delivered"].get("incident.json", 0) >= 1)
        recovering.set()
        assert _until(lambda: pump.status()["delivered"].get("status.json", 0) >= 2)
        assert ("status.json", b"new") in calls
        assert pump.status()["last_error"].get("status.json") is None
    finally:
        pump.stop()


def test_no_mutable_snapshot_reads_in_sender_background(tmp_path: Path):
    received = []
    pump = BoundedTelemetryPump(lambda n, b: received.append((n, b)) or "google_drive_api")
    snapshot = tmp_path / "status.json"
    try:
        snapshot.write_bytes(b"one")
        pump.submit("status.json", snapshot.read_bytes())
        snapshot.write_bytes(b"two")
        assert _until(lambda: pump.status()["delivered"].get("status.json", 0) == 1)
        assert received[0] == ("status.json", b"one")
    finally:
        pump.stop()


def test_supervisor_mirror_is_enqueue_only_without_network_call(tmp_path: Path):
    class Pump:
        def __init__(self):
            self.items = []

        def submit(self, name, data):
            self.items.append((name, data))
            return 1

    service = LocalOnlyProductionSupervisorService.__new__(
        LocalOnlyProductionSupervisorService
    )
    service._telemetry_pump = Pump()
    service._mirror_last_error = ""
    valid = tmp_path / "status.json"
    valid.write_text(
        json.dumps({
            "schema": "ua-free-autopilot-supervisor-v2",
            "version": V2_VERSION,
            "generated_at": "2026-10-25T18:01:00+02:00",
        }),
        encoding="utf-8",
    )
    service._mirror_file(valid, "status.json")
    assert service._telemetry_pump.items == [("status.json", valid.read_bytes())]
    assert service._mirror_last_error == ""

    invalid = tmp_path / "bad.json"
    invalid.write_text('{"version":"0.0.0"}', encoding="utf-8")
    service._mirror_file(invalid, "status.json")
    assert len(service._telemetry_pump.items) == 1
    assert "invalid telemetry" in service._mirror_last_error


def test_old_operator_allowlist_and_safety_are_unchanged():
    assert frozenset(TELEMETRY_NAMES) == _OUTBOUND_TELEMETRY_FILES
    assert "operator_data_current.sqlite3" not in TELEMETRY_NAMES
