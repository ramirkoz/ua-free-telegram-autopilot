from __future__ import annotations

import queue
import time
from types import SimpleNamespace


def test_rc55_installer_rebinds_stale_ui_refresh_symbols(monkeypatch):
    import telegram_autopilot.rc48_ui as rc48_ui
    import telegram_autopilot.rc51_ui as rc51_ui
    import telegram_autopilot.rc55_refresh as rc55
    from telegram_autopilot.ui import MainWindow

    monkeypatch.setattr(rc55, "_INSTALLED", False)
    rc55.install_rc55_refresh()

    assert rc48_ui.refresh_channel_metrics is rc55.refresh_feedback_metrics_rc54
    assert rc51_ui.refresh_feedback_metrics is rc55.refresh_feedback_metrics_rc54
    assert MainWindow._rc48_refresh_metrics_now is rc55.refresh_metrics_now_rc55


def test_rc55_worker_failure_always_returns_ui_from_busy_state(monkeypatch):
    import telegram_autopilot.rc55_refresh as rc55

    def explode(*args, **kwargs):
        raise RuntimeError("synthetic refresh failure")

    monkeypatch.setattr(rc55, "refresh_feedback_metrics_rc54", explode)

    warnings = []
    monkeypatch.setattr(rc55.messagebox, "showwarning", lambda *args, **kwargs: warnings.append(args[1]))
    monkeypatch.setattr(rc55.messagebox, "showinfo", lambda *args, **kwargs: None)

    class Status:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

        def __bool__(self):
            return True

    class Db:
        def get_channel(self, channel_id):
            return SimpleNamespace(id=channel_id, name="TEST", telegram_chat_id="test")

    ui_queue = queue.Queue()
    fake = SimpleNamespace(
        current_channel_id=2,
        db=Db(),
        root=None,
        rc51_feedback_status=Status(),
        _ui_queue=ui_queue,
        _rc48_refresh_memory=lambda: None,
    )

    rc55.refresh_metrics_now_rc55(fake)
    assert getattr(fake, rc55._INFLIGHT_ATTR) is True

    finish = ui_queue.get(timeout=3)
    finish()

    assert getattr(fake, rc55._INFLIGHT_ATTR) is False
    assert warnings == ["Telegram Analytics: synthetic refresh failure"]


def test_rc55_second_channel_uses_rc54_transport_again(monkeypatch):
    import telegram_autopilot.rc55_refresh as rc55

    calls = []

    def fake_refresh(db, channel, *, force=False):
        calls.append((channel.id, force))
        return {
            "configured": True,
            "checked": 1,
            "saved": 1,
            "error": "",
            "policy_warning": "",
        }

    monkeypatch.setattr(rc55, "refresh_feedback_metrics_rc54", fake_refresh)
    monkeypatch.setattr(rc55.messagebox, "showwarning", lambda *args, **kwargs: None)
    monkeypatch.setattr(rc55.messagebox, "showinfo", lambda *args, **kwargs: None)

    class Status:
        def set(self, value):
            pass

        def __bool__(self):
            return True

    class Db:
        def get_channel(self, channel_id):
            return SimpleNamespace(id=channel_id, name=f"CH{channel_id}", telegram_chat_id=f"ch{channel_id}")

    ui_queue = queue.Queue()
    fake = SimpleNamespace(
        current_channel_id=1,
        db=Db(),
        root=None,
        rc51_feedback_status=Status(),
        _ui_queue=ui_queue,
        _rc48_refresh_memory=lambda: None,
    )

    rc55.refresh_metrics_now_rc55(fake)
    ui_queue.get(timeout=3)()
    fake.current_channel_id = 2
    rc55.refresh_metrics_now_rc55(fake)
    ui_queue.get(timeout=3)()

    assert calls == [(1, True), (2, True)]
