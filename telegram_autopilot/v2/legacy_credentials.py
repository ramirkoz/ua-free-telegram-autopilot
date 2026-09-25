from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from ..paths import data_dir, secret_key_path, secrets_path
from .migration import locate_legacy_database
from .storage import now_iso


def legacy_data_dir(path: str | Path) -> Path:
    db = locate_legacy_database(path)
    return db.parent


def import_legacy_secrets(path: str | Path, *, overwrite: bool = False) -> tuple[bool, str]:
    """Copy the old encrypted Telegram/API credentials without decrypting them.

    ``secrets.key`` and ``secrets.secure`` are a pair.  Each member is staged in
    its own uniquely named temporary file in the destination directory, then
    installed.  The unique names matter on Windows: using ``Path.with_suffix``
    for both files collapses both names to the same ``secrets.migration.tmp``.

    Existing V2 credentials are never overwritten unless ``overwrite=True``.
    If installation of either member fails, the previous pair is restored (or
    a newly installed partial pair is removed).
    """
    old_dir = legacy_data_dir(path)
    old_key = old_dir / "secrets.key"
    old_secure = old_dir / "secrets.secure"
    if not old_key.exists() or not old_secure.exists():
        return False, "У старій Data немає пари secrets.key + secrets.secure."

    target_key = secret_key_path()
    target_secure = secrets_path()
    target_key.parent.mkdir(parents=True, exist_ok=True)
    target_secure.parent.mkdir(parents=True, exist_ok=True)

    had_key = target_key.exists()
    had_secure = target_secure.exists()
    if (had_key or had_secure) and not overwrite:
        return False, "У V2 вже є credentials; автоматичне перезаписування заборонено."

    token = uuid.uuid4().hex
    temp_key = target_key.with_name(target_key.name + f".{token}.migration.tmp")
    temp_secure = target_secure.with_name(target_secure.name + f".{token}.migration.tmp")

    backup_key: Path | None = None
    backup_secure: Path | None = None
    if overwrite and (had_key or had_secure):
        backup = data_dir() / "migration_backups" / (
            "credentials-" + now_iso().replace(":", "-") + "-" + token[:8]
        )
        backup.mkdir(parents=True, exist_ok=True)
        if had_key:
            backup_key = backup / target_key.name
            shutil.copy2(target_key, backup_key)
        if had_secure:
            backup_secure = backup / target_secure.name
            shutil.copy2(target_secure, backup_secure)

    installed_key = False
    installed_secure = False
    try:
        shutil.copy2(old_key, temp_key)
        shutil.copy2(old_secure, temp_secure)
        if temp_key.stat().st_size <= 0 or temp_secure.stat().st_size <= 0:
            raise ValueError("Legacy credentials pair contains an empty file")

        temp_key.replace(target_key)
        installed_key = True
        temp_secure.replace(target_secure)
        installed_secure = True
        return True, "Зашифровані Telegram/API credentials перенесено без розшифрування."
    except Exception:
        # Restore the exact pre-import state.  This prevents a half-installed
        # key/blob pair from making all providers look misconfigured later.
        try:
            if had_key and backup_key is not None and backup_key.exists():
                shutil.copy2(backup_key, target_key)
            elif installed_key and not had_key:
                target_key.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            if had_secure and backup_secure is not None and backup_secure.exists():
                shutil.copy2(backup_secure, target_secure)
            elif installed_secure and not had_secure:
                target_secure.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        for temp in (temp_key, temp_secure):
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
