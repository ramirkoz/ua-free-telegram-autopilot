"""Regression: V2 toolbar button runs real probes and refreshes displayed results."""
from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch
from telegram_autopilot.v2.domain import ProviderHealth, ProviderState
from telegram_autopilot.v2.main import MainWindow

class FakeWindow:
    test_ai = MainWindow.test_ai
    def __init__(self):
        self.status=MagicMock()
        self.runtime=MagicMock()
        self.runtime.gateway.probe_all.return_value=[
            ProviderHealth(provider="gemini",state=ProviderState.HEALTHY),
            ProviderHealth(provider="nvidia",state=ProviderState.NETWORK_DOWN),
            ProviderHealth(provider="groq",state=ProviderState.HEALTHY),
            ProviderHealth(provider="cloudflare",state=ProviderState.UNKNOWN),
            ProviderHealth(provider="openrouter",state=ProviderState.HEALTHY),
            ProviderHealth(provider="local",state=ProviderState.HEALTHY),
            ProviderHealth(provider="codex",state=ProviderState.CONFIG_ERROR,detail="не налаштовано"),
        ]
        self.refresh_ai=MagicMock()
        self.refresh_codex_status=MagicMock()
        self.refresh_home=MagicMock()
        self.callbacks=[]
    def after(self,delay,callback):
        self.callbacks.append(callback)

class InlineThread:
    def __init__(self,target,**kw):self.target=target
    def start(self):self.target()
class DelayedThread:
    def __init__(self,target,**kw):self.target=target
    def start(self):pass

class TestV236(unittest.TestCase):
    def test_toolbar_invokes_probes_and_refreshes_ui(self):
        w=FakeWindow()
        with patch("telegram_autopilot.v2.main.threading.Thread",InlineThread):w.test_ai()
        w.runtime.gateway.probe_all.assert_called_once_with()
        self.assertEqual(len(w.callbacks),1)
        w.callbacks.pop()()
        self.assertFalse(w._manual_ai_test_running)
        self.assertIn("перевірено 6",w.status.set.call_args.args[0])
        self.assertIn("працює 4",w.status.set.call_args.args[0])
        self.assertIn("пропущено 1",w.status.set.call_args.args[0])
        w.refresh_ai.assert_called_once()
        w.refresh_codex_status.assert_called_once()

    def test_repeated_clicks_do_not_launch_concurrent_paid_probes(self):
        w=FakeWindow()
        with patch("telegram_autopilot.v2.main.threading.Thread",DelayedThread):
            w.test_ai()
            w.test_ai()
        self.assertTrue(w._manual_ai_test_running)
        self.assertIn("вже виконується",w.status.set.call_args.args[0])

    def test_probe_exception_returns_error_and_unblocks_button(self):
        w=FakeWindow()
        w.runtime.gateway.probe_all.side_effect=RuntimeError("network test failed")
        with patch("telegram_autopilot.v2.main.threading.Thread",InlineThread):w.test_ai()
        w.callbacks.pop()()
        self.assertFalse(w._manual_ai_test_running)
        self.assertIn("network test failed",w.status.set.call_args.args[0])
        w.refresh_ai.assert_called_once()

if __name__=="__main__":unittest.main()
