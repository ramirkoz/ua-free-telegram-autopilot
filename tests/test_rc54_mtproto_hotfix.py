from __future__ import annotations

import asyncio
import sys
import threading
import types


def _fake_telethon(monkeypatch):
    state = {"root_used": False, "clients": []}
    telethon = types.ModuleType("telethon")
    sync = types.ModuleType("telethon.sync")
    errors = types.ModuleType("telethon.errors")
    sessions = types.ModuleType("telethon.sessions")

    class SessionPasswordNeededError(Exception):
        pass

    class StringSession:
        def __init__(self, value=""):
            self.value = value

    class SavedSession:
        def save(self):
            return "SESSION_OK"

    class FakeClient:
        def __init__(self, session, api_id, api_hash, **kwargs):
            self.api_id = api_id
            self.session = SavedSession()
            self.authorized = False
            self.disconnected = False
            state["clients"].append(self)

        def connect(self):
            assert not asyncio.get_event_loop().is_closed()

        def disconnect(self):
            self.disconnected = True

        def is_user_authorized(self):
            return self.authorized

        def send_code_request(self, phone):
            assert phone == "+380000000000"
            return types.SimpleNamespace(phone_code_hash="HASH")

        def sign_in(self, **kwargs):
            assert kwargs.get("code") == "12345"
            self.authorized = True

        def get_me(self):
            return types.SimpleNamespace(first_name="Test", last_name="Operator", username="tester")

    class RootTrap:
        def __init__(self, *args, **kwargs):
            state["root_used"] = True
            raise AssertionError("async TelegramClient root import must not be used")

    telethon.TelegramClient = RootTrap
    sync.TelegramClient = FakeClient
    errors.SessionPasswordNeededError = SessionPasswordNeededError
    sessions.StringSession = StringSession
    telethon.sync = sync
    telethon.errors = errors
    telethon.sessions = sessions
    monkeypatch.setitem(sys.modules, "telethon", telethon)
    monkeypatch.setitem(sys.modules, "telethon.sync", sync)
    monkeypatch.setitem(sys.modules, "telethon.errors", errors)
    monkeypatch.setitem(sys.modules, "telethon.sessions", sessions)
    return state


def test_rc54_authorization_is_blocking_sync_inside_worker(monkeypatch):
    state = _fake_telethon(monkeypatch)
    from telegram_autopilot.rc54_mtproto import authorize_telegram_analytics_rc54
    result = []
    errors = []

    def worker():
        try:
            result.append(authorize_telegram_analytics_rc54(
                api_id=123,
                api_hash="hash",
                phone="+380000000000",
                code_callback=lambda: "12345",
                password_callback=lambda: "unused",
            ))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start(); thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert result == [("SESSION_OK", "Test Operator (@tester)")]
    assert state["root_used"] is False
    assert state["clients"][0].disconnected is True


def test_rc54_sync_client_creates_worker_event_loop(monkeypatch):
    _fake_telethon(monkeypatch)
    from telegram_autopilot.rc54_mtproto import _sync_client
    result = []

    def worker():
        asyncio.set_event_loop(None)
        with _sync_client(session="", api_id=1, api_hash="hash") as client:
            result.append(client.api_id)

    thread = threading.Thread(target=worker)
    thread.start(); thread.join(timeout=5)
    assert not thread.is_alive()
    assert result == [1]


def test_rc54_installer_replaces_broken_rc53_symbols(monkeypatch):
    import telegram_autopilot.rc48_learning as rc48
    import telegram_autopilot.rc51_feedback as rc51
    import telegram_autopilot.rc53_ui as rc53_ui
    import telegram_autopilot.rc54_mtproto as rc54

    monkeypatch.setattr(rc54, "_INSTALLED", False)
    rc54.install_rc54_mtproto()
    assert rc48.authorize_telegram_analytics is rc54.authorize_telegram_analytics_rc54
    assert rc48.refresh_channel_metrics is rc54.refresh_feedback_metrics_rc54
    assert rc51.refresh_feedback_metrics is rc54.refresh_feedback_metrics_rc54
    assert rc53_ui.authorize_telegram_analytics is rc54.authorize_telegram_analytics_rc54
    assert rc53_ui._analytics_dialog_rc53 is rc54._analytics_dialog_rc54
