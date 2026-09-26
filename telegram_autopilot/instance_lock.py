from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import BinaryIO

from .paths import lock_path


class AlreadyRunning(RuntimeError):
    pass


class InstanceLock:
    """Single-instance guard.

    On Windows use a named kernel mutex so the portable directory is not kept
    artificially locked by a file handle.  Non-Windows CI/dev keeps the simple
    advisory file lock.
    """

    _WINDOWS_MUTEX_NAME = "Local\\UA_FREE_Telegram_Autopilot_V2"
    _ERROR_ALREADY_EXISTS = 183

    def __init__(self, path: Path | None = None):
        self.path = path or lock_path()
        self.handle: BinaryIO | None = None
        self.mutex_handle = None

    def __enter__(self):
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            mutex = kernel32.CreateMutexW(None, False, self._WINDOWS_MUTEX_NAME)
            if not mutex:
                raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
            if ctypes.get_last_error() == self._ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(ctypes.c_void_p(mutex))
                raise AlreadyRunning("UA FREE Telegram Autopilot уже запущено.")
            self.mutex_handle = mutex
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0)
        import fcntl
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise AlreadyRunning("UA FREE Telegram Autopilot уже запущено.") from exc
        self.handle = handle
        return self

    def __exit__(self, *_):
        if os.name == "nt":
            mutex = self.mutex_handle
            self.mutex_handle = None
            if mutex:
                try:
                    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                    kernel32.ReleaseMutex(ctypes.c_void_p(mutex))
                finally:
                    kernel32.CloseHandle(ctypes.c_void_p(mutex))
            return

        if not self.handle:
            return
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
