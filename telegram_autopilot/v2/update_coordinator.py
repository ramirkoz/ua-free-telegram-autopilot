from __future__ import annotations

import os
import threading
from typing import Any

from .loghub import event
from .update_protocol import UpdateProtocol, UpdateRequest, checkpoint_database


class UpdateCoordinator:
    """Bridge a validated remote request to the detached update transaction.

    The live application deliberately does *not* wait for workers/collectors to
    quiesce before launching the updater.  A blocked HTTP request must never be
    able to veto an approved release.  The coordinator creates a consistent DB
    backup while the application is still healthy, starts the detached helper,
    and leaves ownership of shutdown/apply/verify/rollback to that helper.
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
        try:
            self.app.status.set(f"Перевіряю та готую оновлення до {request.target_version}…")
        except Exception:
            pass
        event(
            "update", "external update transaction requested",
            target_version=request.target_version, request_id=request.request_id,
        )

        def work() -> None:
            helper = None
            try:
                # SQLite backup() is a consistent snapshot even while the runtime is
                # processing jobs.  WAL checkpoint is useful housekeeping but must
                # not become another way for a busy worker to block an update.
                checkpoint = "wal_checkpoint=not_required"
                try:
                    checkpoint = checkpoint_database(self.store)
                except Exception as exc:
                    checkpoint = f"wal_checkpoint_warning={type(exc).__name__}: {exc}"

                self.protocol.write_state("PREPARING_TRANSACTION", request=request, detail=checkpoint)
                db_backup = self.protocol.backup_database(self.store, request)
                self.protocol.write_ready(
                    request,
                    pid=os.getpid(),
                    detail=f"{checkpoint}; db_backup={db_backup}; detached_runner_owns_shutdown=true",
                )
                self.protocol.clear_health_marker()
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)

                # Start the updater while this process is still known-good.  The
                # helper performs download/SHA/stage validation first.  Only then
                # may it terminate this parent process, and it never kills its own
                # detached process tree.
                helper = self.protocol.launch_helper(request, parent_pid=os.getpid())
                event(
                    "update", "detached transaction runner launched",
                    target_version=request.target_version,
                    request_id=request.request_id,
                    helper_pid=int(getattr(helper, "pid", 0) or 0),
                )

                # Do not close the GUI here.  If preflight fails the current RC must
                # keep running.  On a valid package the helper itself terminates this
                # exact parent PID and owns the rest of the transaction.
                exit_code = helper.wait()
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                # Reaching this line means the parent survived the helper.  A
                # successful installation would have terminated this process.
                raise RuntimeError(f"UPDATE_RUNNER_EXITED_WITH_PARENT_ALIVE code={exit_code}")
            except Exception as exc:
                event(
                    "update", "detached update preparation/runner failed", level=40,
                    target_version=request.target_version, detail=str(exc)[:1200],
                )
                # The helper writes the authoritative failure/rollback result when
                # it started successfully.  Only synthesize PREPARE_FAILED if there
                # is no terminal helper result yet.
                terminal = False
                try:
                    terminal = self.protocol.request_already_terminal(request)
                except Exception:
                    terminal = False
                if not terminal:
                    self.protocol.write_result(
                        "FAILED", request=request,
                        detail=f"PREPARE_FAILED: {type(exc).__name__}: {exc}",
                    )
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                self._inflight = False
                message = f"Оновлення не застосовано: {exc}"
                try:
                    self.app.after(0, lambda msg=message: self._show_failure(msg))
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True, name="V2-Update-Transaction-Handoff").start()

    def _show_failure(self, message: str) -> None:
        try:
            self.app.status.set(message)
        except Exception:
            pass
        self._schedule(10000)

    def _close_for_update(self) -> None:
        """Compatibility hook retained for older callers.

        RC37 does not call this from the coordinator.  Shutdown is owned by the
        detached updater after package preflight succeeds.
        """
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
