from __future__ import annotations

from .production_supervisor import ProductionSupervisorService
from .responsive_ui import ResponsiveMainWindow


class ProductionMainWindow(ResponsiveMainWindow):
    """RC22 UI shell using the unambiguous LIVE remote supervisor feed."""

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)
        try:
            self.supervisor.stop()
        except Exception:
            pass
        self.supervisor = ProductionSupervisorService(store, runtime, logs_dir)
        self.supervisor.start()

    def start_runtime(self):
        if not getattr(self, "_startup_ready", False):
            return super().start_runtime()
        try:
            # Publish intended state before workers start. If RuntimeEngine.start()
            # fails, the next snapshot corrects it from authoritative runtime state.
            self.supervisor.set_expected_running(True)
        except Exception:
            pass
        return super().start_runtime()
