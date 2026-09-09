from __future__ import annotations

import shutil
from pathlib import Path

from ..paths import data_dir, secret_key_path, secrets_path
from .migration import locate_legacy_database
from .storage import now_iso


def legacy_data_dir(path: str | Path) -> Path:
    db = locate_legacy_database(path)
    return db.parent


def import_legacy_secrets(path: str | Path, *, overwrite: bool = False) -> tuple[bool, str]:
    """Copy the old encrypted Telegram/API credentials as an atomic pair.

    The encryption format is unchanged. The function never decrypts or logs secrets.
    Existing V2 credentials are backed up before an explicit overwrite.
    """
    old_dir = legacy_data_dir(path)
    old_key = old_dir / "secrets.key"
    old_secure = old_dir / "secrets.secure"
    if not old_key.exists() or not old_secure.exists():
        return False, "У старій Data немає пари secrets.key + secrets.secure."

    target_key = secret_key_path()
    target_secure = secrets_path()
    if (target_key.exists() or target_secure.exists()) and not overwrite:
        return False, "У V2 вже є credentials; автоматичне перезаписування заборонено."

    if overwrite:
        backup = data_dir() / "migration_backups" / now_iso().replace(":", "-")
        backup.mkdir(parents=True, exist_ok=True)
        for current in (target_key, target_secure):
            if current.exists():
                shutil.copy2(current, backup / current.name)

    temp_key = target_key.with_suffix(".migration.tmp")
    temp_secure = target_secure.with_suffix(".migration.tmp")
    shutil.copy2(old_key, temp_key)
    shutil.copy2(old_secure, temp_secure)
    temp_key.replace(target_key)
    temp_secure.replace(target_secure)
    return True, "Зашифровані Telegram/API credentials перенесено без розшифрування."
