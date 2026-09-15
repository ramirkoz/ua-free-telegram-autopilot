from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..paths import runtime_dir
from .update_protocol import UpdateProtocol, UpdateRequest


class SafeUpdateProtocol(UpdateProtocol):
    """Launch the SHA-aware detached updater used by RC32+ remote updates."""

    def launch_helper(self, request: UpdateRequest, *, parent_pid: int) -> subprocess.Popen[Any]:
        root = runtime_dir()
        console = root / "_runtime_console.exe"
        if console.is_file():
            executable = str(console)
            args = [executable, "-I", "-m", "telegram_autopilot.v2.safe_updater_helper"]
        else:
            executable = sys.executable
            args = [executable, "-m", "telegram_autopilot.v2.safe_updater_helper"]
        args += ["--request", str(self.request_path), "--parent-pid", str(int(parent_pid))]
        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(getattr(subprocess, "DETACHED_PROCESS", 0))
        self.write_state("UPDATER_LAUNCHED", request=request, helper=Path(executable).name, helper_module="safe_updater_helper")
        return subprocess.Popen(
            args,
            cwd=str(root),
            close_fds=(os.name != "nt"),
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
