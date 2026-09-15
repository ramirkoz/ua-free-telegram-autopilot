from __future__ import annotations

from . import ui as base_ui
from .responsive_ui import ResponsiveMainWindow
from .local_supervisor import LocalOnlyProductionSupervisorService as ProductionSupervisorService


class ProductionMainWindow(ResponsiveMainWindow):
    """Production UI with exactly one local-only supervisor from first paint."""

    def __init__(self, store, runtime, logs_dir):
        # Initialise the responsive shell fields here, then let the base UI create
        # the RC40 local-only production supervisor directly and start it once.
        self._rc20_closing = False
        self._rc20_runtime_action = False
        self._rc20_last_refresh: dict[str, float] = {}
        self._rc20_heartbeat_after = None

        original = base_ui.SupervisorService
        base_ui.SupervisorService = ProductionSupervisorService
        try:
            base_ui.MainWindow.__init__(self, store, runtime, logs_dir)
        finally:
            base_ui.SupervisorService = original

        self.book.bind("<<NotebookTabChanged>>", self._rc20_tab_changed, add="+")
        self._rc20_ui_heartbeat()

    def start_runtime(self):
        if not getattr(self, "_startup_ready", False):
            return super().start_runtime()
        try:
            self.supervisor.set_expected_running(True)
        except Exception:
            pass
        return super().start_runtime()
