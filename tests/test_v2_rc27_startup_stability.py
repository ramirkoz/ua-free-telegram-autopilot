from __future__ import annotations

import inspect
import json

from telegram_autopilot.v2 import fileio, production_supervisor, production_ui


def test_production_ui_does_not_chain_three_supervisors():
    source = inspect.getsource(production_ui.ProductionMainWindow.__init__)
    assert "ResponsiveMainWindow.__init__" not in source
    assert "base_ui.MainWindow.__init__" in source
    assert "base_ui.SupervisorService = ProductionSupervisorService" in source
    assert "self.supervisor.stop()" not in source
    assert "self.supervisor.start()" not in source


def test_production_supervisor_uses_hardened_atomic_json(tmp_path):
    target = tmp_path / "recent_events.json"
    production_supervisor.ProductionSupervisorService._atomic_json(target, {"ok": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_atomic_json_retries_transient_windows_style_lock(tmp_path, monkeypatch):
    target = tmp_path / "recent_events.json"
    target.write_text('{"old": true}', encoding="utf-8")
    real_replace = fileio.os.replace
    calls = {"count": 0}

    def flaky_replace(src, dst):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise PermissionError("simulated WinError 32 lock")
        return real_replace(src, dst)

    monkeypatch.setattr(fileio.os, "replace", flaky_replace)
    fileio.atomic_write_json(target, {"ok": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert calls["count"] == 3
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))
