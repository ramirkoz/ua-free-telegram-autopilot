from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from .paths import lock_path


class AlreadyRunning(RuntimeError): pass


class InstanceLock:
    def __init__(self,path:Path|None=None): self.path=path or lock_path(); self.handle:BinaryIO|None=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); h=self.path.open("a+b"); h.seek(0)
        if os.name=="nt":
            import msvcrt
            try: msvcrt.locking(h.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc: h.close(); raise AlreadyRunning("UA FREE Telegram Autopilot уже запущено.") from exc
        else:
            import fcntl
            try: fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc: h.close(); raise AlreadyRunning("UA FREE Telegram Autopilot уже запущено.") from exc
        self.handle=h; return self
    def __exit__(self,*_):
        if not self.handle: return
        try:
            self.handle.seek(0)
            if os.name=="nt":
                import msvcrt; msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl; fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN)
        finally: self.handle.close(); self.handle=None
