"""Bounded, outbound-only telemetry uploader (2.2.33).

A Drive/OAuth/network stall cannot hold the local supervisor heartbeat or
publishing. Only the latest valid payload per known name is retained: no
unbounded retry queue, remote commands, or upload of operator Data.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable


TELEMETRY_NAMES = ("status.json", "recent_events.json", "incident.json")


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class BoundedTelemetryPump:
    """Serialized latest-value uploader with bounded retry and independent health.

    send(name, payload) is invoked by one daemon thread; it may perform the
    Google Drive API upload and a canonical local-sync fallback. Individual
    names back off independently so a broken incident upload cannot starve
    status.json. No caller may supply names outside TELEMETRY_NAMES.
    """

    def __init__(
        self,
        send: Callable[[str, bytes], str],
        *,
        retry_seconds: float = 10.0,
        max_retry_seconds: float = 60.0,
    ) -> None:
        self._send = send
        self._retry = max(0.01, float(retry_seconds))
        self._max_retry = max(self._retry, float(max_retry_seconds))
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: dict[str, tuple[int, bytes]] = {}
        self._next_due: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._submitted: dict[str, int] = {}
        self._delivered: dict[str, int] = {}
        self._last_ok: dict[str, str] = {}
        self._last_error: dict[str, str] = {}
        self._last_mode: dict[str, str] = {}
        self._last_attempt: dict[str, str] = {}

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="Autopilot-Drive-Telemetry-233",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 0.5) -> None:
        self._stop.set()
        self._wake.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(max(0.0, timeout))

    def submit(self, name: str, payload: bytes) -> int:
        if name not in TELEMETRY_NAMES:
            raise ValueError("Telemetry upload not allowlisted")
        if not isinstance(payload, bytes):
            raise TypeError("Telemetry payload must be immutable bytes")
        with self._lock:
            seq = self._submitted.get(name, 0) + 1
            self._submitted[name] = seq
            self._pending[name] = (seq, payload)
        self.start()
        self._wake.set()
        return seq

    def _ready(self) -> tuple[str, int, bytes] | None:
        now = time.monotonic()
        with self._lock:
            for name in TELEMETRY_NAMES:
                task = self._pending.get(name)
                if task is not None and self._next_due.get(name, 0.0) <= now:
                    seq, data = task
                    del self._pending[name]
                    self._last_attempt[name] = _stamp()
                    return name, seq, data
        return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            task = self._ready()
            if task is None:
                with self._lock:
                    next_due = min(
                        (self._next_due.get(name, 0.0) for name in self._pending),
                        default=None,
                    )
                timeout = 1.0 if next_due is None else max(
                    0.02, min(1.0, next_due - time.monotonic())
                )
                self._wake.wait(timeout)
                self._wake.clear()
                continue
            name, seq, data = task
            try:
                mode = str(self._send(name, data) or "google_drive_api")
                if mode not in {"google_drive_api", "local_fallback"}:
                    mode = "google_drive_api"
            except Exception as exc:
                with self._lock:
                    count = self._failures.get(name, 0) + 1
                    self._failures[name] = count
                    self._last_error[name] = (
                        f"{type(exc).__name__}: {exc}"[:500]
                    )
                    self._next_due[name] = time.monotonic() + min(
                        self._max_retry, self._retry * (2 ** min(8, count - 1))
                    )
                    # Preserve an even newer submission, never resurrect an old
                    # payload on top of it.
                    if name not in self._pending:
                        self._pending[name] = (seq, data)
            else:
                with self._lock:
                    self._delivered[name] = max(
                        self._delivered.get(name, 0), seq
                    )
                    self._last_ok[name] = _stamp()
                    self._last_mode[name] = mode
                    self._last_error.pop(name, None)
                    self._failures[name] = 0
                    self._next_due[name] = 0.0

    def status(self) -> dict[str, object]:
        with self._lock:
            thread = self._thread
            return {
                "mode": "bounded_latest_only",
                "thread_alive": bool(thread and thread.is_alive()),
                "pending_files": list(self._pending),
                "pending_count": len(self._pending),
                "submitted": dict(self._submitted),
                "delivered": dict(self._delivered),
                "last_ok": dict(self._last_ok),
                "last_mode": dict(self._last_mode),
                "last_attempt": dict(self._last_attempt),
                "last_error": dict(self._last_error),
                "consecutive_failures": dict(self._failures),
                "remote_control": False,
            }
