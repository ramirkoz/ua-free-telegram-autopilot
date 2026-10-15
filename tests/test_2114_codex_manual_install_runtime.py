"""The portable GUI executable must not be used to invoke pip."""
from pathlib import Path
from unittest.mock import patch
import subprocess

import pytest

from telegram_autopilot import codex_engine


def test_manual_install_uses_bundled_runtime_not_gui(tmp_path):
    gui = tmp_path / "UA_FREE_Telegram_Autopilot.exe"
    runtime = tmp_path / "_runtime_console.exe"
    gui.write_bytes(b"gui")
    runtime.write_bytes(b"python")
    invocations = []

    def run(command, **kwargs):
        invocations.append(command)
        raise RuntimeError("Test intercepted pip")

    with patch.object(codex_engine.sys, "executable", str(gui)), \
         patch.object(codex_engine.os, "name", "nt"), \
         patch.object(codex_engine, "_runtime_root", return_value=tmp_path), \
         patch.object(codex_engine.subprocess, "run", side_effect=run):
        with pytest.raises(RuntimeError, match="intercepted"):
            codex_engine.install_codex()
    assert invocations
    assert Path(invocations[0][0]) == runtime
    assert invocations[0][1:4] == ["-I", "-m", "pip"]
