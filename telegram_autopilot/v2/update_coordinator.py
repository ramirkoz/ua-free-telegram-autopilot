from __future__ import annotations

import os
import threading
from typing import Any

from .loghub import event
from .update_protocol import UpdateProtocol, UpdateRequest, checkpoint_database


class UpdateCoordinator:
    """Bridge the agent file protocol to a graceful V2 shutdown.

    The coordinator deliberately contains no download/install logic. It only watches
    for a validated request, quiesces the live application, flushes and backs up the
    database, starts the detached deterministic updater, then closes the GUI.
    """

    def __init__(self, app: Any, store: Any, runtime: Any) -> None:
        self.app = app
        self.store = store
        self.runtime = runtime
        self.supervisor = app.supervisor
        self.feedback_runtime = app.feedback_runtime
        self.protocol = UpdateProtocol()
        self._inflight = False
        self._after_id: str | None = None
        self._closed = False

    def start(self) -> None:
        if self._closed:
            return
        self._schedule(2500)

    def stop(self) -> None:
        self._closed = True
        after_id = self._after_id
        self._after_id = None
        if after_id:
            try:
                self.app.after_cancel(after_id)
            except Exception:
                pass

    def _schedule(self, delay_ms: int = 5000) -> None:
        if self._closed or self._inflight:
            return
        try:
            if self.app.winfo_exists():
                self._after_id = self.app.after(max(1000, int(delay_ms)), self.poll)
        except Exception:
            self._after_id = None

    def poll(self) -> None:
        self._after_id = None
        if self._closed or self._inflight:
            return
        try:
            request = self.protocol.accept_mirror_request(self.supervisor.config.mirror_dir)
            if request is None:
                request = self.protocol.load_request()
            self.protocol.mirror_status(self.supervisor.config.mirror_dir)
            if request is None:
                self._schedule()
                return
            if self.protocol.request_already_terminal(request):
                self._schedule()
                return
            if not self.protocol.request_is_newer(request):
                self.protocol.write_result(
                    "REJECTED", request=request,
                    detail=f"Target {request.target_version} is not newer than the installed version",
                )
                try:
                    self.protocol.request_path.unlink()
                except FileNotFoundError:
                    pass
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                self._schedule()
                return
            self._begin(request)
        except Exception as exc:
            event("update", "update request poll failed", level=30, detail=str(exc)[:1200])
            self._schedule(10000)

    def _begin(self, request: UpdateRequest) -> None:
        if self._inflight:
            return
        self._inflight = True
        was_running = bool(getattr(self.app, "_running", False))
        try:
            self.app.status.set(f"Готую безпечне оновлення до {request.target_version}…")
        except Exception:
            pass
        event("update", "graceful update requested", target_version=request.target_version, request_id=request.request_id)

        def work() -> None:
            helper_started = False
            try:
                self.supervisor.set_expected_running(False)
                self.protocol.write_state("QUIESCING", request=request)
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                self.feedback_runtime.stop()
                if was_running:
                    self.runtime.stop(timeout=180.0)
                    self.app._running = False
                health = self.runtime.health_snapshot()
                if int(health.get("live_workers") or 0) or int(health.get("live_collectors") or 0):
                    raise RuntimeError("UPDATE_QUIESCE_TIMEOUT")
                checkpoint = checkpoint_database(self.store)
                db_backup = self.protocol.backup_database(self.store, request)
                self.protocol.write_ready(
                    request,
                    pid=os.getpid(),
                    detail=f"{checkpoint}; db_backup={db_backup}",
                )
                self.protocol.clear_health_marker()
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                self.protocol.launch_helper(request, parent_pid=os.getpid())
                helper_started = True
                event("update", "external updater launched", target_version=request.target_version, request_id=request.request_id)
                self.app.after(0, self._close_for_update)
            except Exception as exc:
                event(
                    "update", "graceful update preparation failed", level=40,
                    target_version=request.target_version, detail=str(exc)[:1200],
                )
                self.protocol.write_result(
                    "FAILED", request=request,
                    detail=f"PREPARE_FAILED: {type(exc).__name__}: {exc}",
                )
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                if not helper_started:
                    try:
                        if was_running:
                            self.runtime.start()
                            self.app._running = True
                            self.supervisor.set_expected_running(True)
                        if bool(getattr(self.app, "_feedback_ready", False)):
                            self.feedback_runtime.start()
                    except Exception as restart_exc:
                        event(
                            "update", "runtime restart after failed update preparation failed",
                            level=40, detail=str(restart_exc)[:1000],
                        )
                self._inflight = False
                message = f"Оновлення не застосовано: {exc}"
                try:
                    self.app.after(0, lambda msg=message: self._show_failure(msg))
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True, name="V2-Graceful-Updater").start()

    def _show_failure(self, message: str) -> None:
        try:
            self.app.status.set(message)
        except Exception:
            pass
        self._schedule(10000)

    def _close_for_update(self) -> None:
        self.stop()
        try:
            refresh_id = getattr(self.app, "_refresh_after_id", None)
            if refresh_id is not None:
                try:
                    self.app.after_cancel(refresh_id)
                except Exception:
                    pass
                self.app._refresh_after_id = None
            self.feedback_runtime.stop()
            self.supervisor.stop()
        finally:
            self.app.destroy()
