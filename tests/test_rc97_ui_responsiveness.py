from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
UI = ROOT / "telegram_autopilot" / "v2" / "ui_hardening.py"
SUPERVISOR = ROOT / "telegram_autopilot" / "v2" / "advanced_supervisor.py"


def test_rc97_skips_periodic_heavy_refresh_when_window_hidden() -> None:
    source = UI.read_text(encoding="utf-8")
    assert "def _rc97_window_visible" in source
    assert "if not self._rc97_window_visible():" in source
    assert "self.after(2500, self.refresh_all)" in source


def test_rc97_debounces_tab_changes() -> None:
    source = UI.read_text(encoding="utf-8")
    assert "def _rc20_tab_changed" in source
    assert "self.after_cancel(self._rc97_tab_after)" in source
    assert "self.after(120, self._rc97_refresh_after_tab_change)" in source


def test_rc97_tree_refresh_yields_and_avoids_rewriting_unchanged_rows() -> None:
    source = UI.read_text(encoding="utf-8")
    assert "batch_size = 12" in source
    assert "yield_ms = 8" in source
    assert "existing_values.get(iid) != tuple(str(v) for v in values)" in source
    assert "if not order_unchanged and tree.index(iid) != index" in source


def test_rc97_records_event_loop_lag_in_supervisor_snapshot() -> None:
    ui = UI.read_text(encoding="utf-8")
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    assert "ui_event_loop_lag_ms" in ui
    assert "ui_event_loop_peak_lag_ms" in ui
    assert '"event_loop_lag_ms"' in supervisor
    assert '"event_loop_peak_lag_ms"' in supervisor
    assert '"UI_LAGGING"' in supervisor
