from __future__ import annotations

import queue
import threading
import time
from typing import Callable

from .loghub import event
from .production_ui import ProductionMainWindow


class FastMainWindow(ProductionMainWindow):
    """RC50 UI: worker threads never call Tcl/Tk and unchanged views are not repainted."""

    def __init__(self, store, runtime, logs_dir):
        self._rc50_results: queue.Queue[tuple[str, object, Exception | None, int, int]] = queue.Queue()
        self._rc50_render_signatures: dict[str, int] = {}
        self._rc50_pump_after = None
        super().__init__(store, runtime, logs_dir)
        self._rc50_result_pump()

    def _rc20_async_refresh(self, key: str, work: Callable[[], object], apply: Callable[[object], None]) -> None:
        if self._rc20_closing:
            return
        inflight = self._rc20_data_refresh_inflight
        if key in inflight:
            return
        inflight.add(key)
        started = time.monotonic()

        def worker() -> None:
            result: object = None
            error: Exception | None = None
            signature = 0
            try:
                result = work()
                signature = hash(repr(result))
            except Exception as exc:
                error = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            # Deliberately no self.after()/widget/Tk call here. Tkinter is not a
            # cross-thread message bus; doing that intermittently froze RC49.
            self._rc50_results.put((key, (apply, result), error, elapsed_ms, signature))

        threading.Thread(target=worker, daemon=True, name=f"V2-UI-Refresh-{key}").start()

    def _rc50_result_pump(self) -> None:
        if self._rc20_closing:
            return
        for _ in range(6):
            try:
                key, payload, error, elapsed_ms, signature = self._rc50_results.get_nowait()
            except queue.Empty:
                break
            self._rc20_data_refresh_inflight.discard(key)
            try:
                self.runtime.ui_last_refresh_ms = elapsed_ms
            except Exception:
                pass
            if error is not None:
                event("ui", "background refresh failed", level=30, view=key, elapsed_ms=elapsed_ms, detail=str(error)[:1200])
                continue
            apply, result = payload  # type: ignore[misc]
            if self._rc50_render_signatures.get(key) == signature:
                continue
            try:
                apply(result)
                self._rc50_render_signatures[key] = signature
            except Exception as exc:
                event("ui", "background refresh apply failed", level=30, view=key, detail=str(exc)[:1200])
        try:
            self._rc50_pump_after = self.after(120, self._rc50_result_pump)
        except Exception:
            self._rc50_pump_after = None

    def refresh_all(self):
        if self._rc20_closing:
            return
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None

        key = self._active_tab_key()
        ttl = {
            "home": 5.0,
            "channels": 20.0,
            "queue": 15.0,
            "history": 30.0,
            "ai": 15.0,
            "learning": 60.0,
            "supervisor": 5.0,
        }.get(key, 45.0)
        now = time.monotonic()
        self.runtime.ui_refresh_inflight = True
        try:
            if now - float(self._rc20_last_refresh.get(key, 0.0)) >= ttl:
                fn = {
                    "home": self.refresh_home,
                    "channels": self.refresh_channels,
                    "queue": self.refresh_queue,
                    "history": self.refresh_history,
                    "ai": self.refresh_ai,
                    "learning": self.refresh_learning,
                    "supervisor": self.refresh_supervisor,
                }.get(key)
                if fn is not None:
                    try:
                        fn()
                    except Exception as exc:
                        event("ui", "refresh dispatch failed", level=30, view=key, detail=str(exc)[:1200])
                self._rc20_last_refresh[key] = now
        finally:
            self.runtime.ui_refresh_inflight = False
            try:
                if self.winfo_exists() and not self._rc20_closing:
                    self._refresh_after_id = self.after(1500, self.refresh_all)
            except Exception:
                self._refresh_after_id = None
