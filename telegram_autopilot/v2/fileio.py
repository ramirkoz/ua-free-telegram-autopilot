from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_RETRYABLE_WINERRORS = {5, 32, 33}


def unique_temp_path(target: Path) -> Path:
    target = Path(target)
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
    return target.with_name(f".{target.name}.{token}.tmp")


def replace_with_retry(
    temp: Path,
    target: Path,
    *,
    attempts: int = 18,
    initial_delay: float = 0.04,
    max_delay: float = 0.30,
) -> None:
    """Atomic replace resilient to short Windows/Google Drive file locks."""
    temp = Path(temp)
    target = Path(target)
    delay = max(0.01, float(initial_delay))
    total = max(1, int(attempts))
    for attempt in range(total):
        try:
            os.replace(temp, target)
            return
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            retryable = isinstance(exc, PermissionError) or winerror in _RETRYABLE_WINERRORS
            if not retryable or attempt + 1 >= total:
                raise
            time.sleep(delay)
            delay = min(float(max_delay), delay * 1.5)


def atomic_write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = unique_temp_path(path)
    try:
        temp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        replace_with_retry(temp, path)
    finally:
        try:
            temp.unlink()
        except (FileNotFoundError, OSError):
            pass


def atomic_copy(source: Path, target: Path) -> None:
    source = Path(source)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = unique_temp_path(target)
    try:
        shutil.copy2(source, temp)
        replace_with_retry(temp, target)
    finally:
        try:
            temp.unlink()
        except (FileNotFoundError, OSError):
            pass
