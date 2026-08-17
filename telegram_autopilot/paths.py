from __future__ import annotations

import os
import stat
import sys
from functools import lru_cache
from pathlib import Path

APP_DIR = "UA_FREE_Telegram_Autopilot"
PORTABLE_MARKER = "portable.flag"
DATA_DIR_NAME = "Data"


def _has_reparse_attribute(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attrs = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attrs & reparse)


def _reject_reparse_chain(path: Path) -> None:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor) if absolute.anchor else Path()
    for part in absolute.parts[1:] if absolute.anchor else absolute.parts:
        current = current / part
        if current.exists() and _has_reparse_attribute(current):
            raise RuntimeError(f"Data path contains a symlink or reparse point: {current}")


@lru_cache(maxsize=1)
def runtime_dir() -> Path:
    override = os.environ.get("UA_FREE_TELEGRAM_AUTOPILOT_ROOT")
    if override:
        return Path(override).expanduser().absolute()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def data_dir() -> Path:
    override = os.environ.get("UA_FREE_TELEGRAM_AUTOPILOT_DATA")
    root = Path(override).expanduser() if override else runtime_dir() / DATA_DIR_NAME
    _reject_reparse_chain(root.parent)
    root.mkdir(parents=True, exist_ok=True)
    _reject_reparse_chain(root)
    return root


def database_path() -> Path:
    return data_dir() / "telegram_autopilot.sqlite3"


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def secret_key_path() -> Path:
    return data_dir() / "secrets.key"


def secrets_path() -> Path:
    return data_dir() / "secrets.secure"


def ai_state_path() -> Path:
    return data_dir() / "ai_router_state.json"


def lock_path() -> Path:
    return data_dir() / "instance.lock"
