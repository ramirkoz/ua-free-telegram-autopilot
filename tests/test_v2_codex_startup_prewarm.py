from __future__ import annotations

import threading
import time
from pathlib import Path

from telegram_autopilot.v2 import provider_compat


def test_codex_prewarm_serializes_first_import(monkeypatch, tmp_path: Path):
    package = tmp_path / "openai_codex"
    package.mkdir()

    monkeypatch.setattr(provider_compat, "codex_extension_dir", lambda: tmp_path)
    provider_compat._CODEX_PREWARMED = False

    calls = []
    active = 0
    max_active = 0
    guard = threading.Lock()

    def fake_import(name: str):
        nonlocal active, max_active
        assert name == "openai_codex"
        with guard:
            active += 1
            max_active = max(max_active, active)
            calls.append(name)
        time.sleep(0.03)
        with guard:
            active -= 1
        return object()

    monkeypatch.setattr(provider_compat.importlib, "import_module", fake_import)

    results: list[bool] = []
    threads = [threading.Thread(target=lambda: results.append(provider_compat.prewarm_codex_sdk())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert results == [True] * 8
    assert calls == ["openai_codex"]
    assert max_active == 1


def test_codex_prewarm_is_safe_when_not_installed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(provider_compat, "codex_extension_dir", lambda: tmp_path)
    provider_compat._CODEX_PREWARMED = False
    assert provider_compat.prewarm_codex_sdk() is False
