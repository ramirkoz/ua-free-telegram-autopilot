from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .legacy_credentials import import_legacy_secrets
from .migration import build_export_bundle, import_legacy_data
from .storage import V2Store, now_iso


class MigrationManager:
    def __init__(self, target_db: str | Path):
        self.target_db = Path(target_db)

    def export_legacy(self, legacy_path: str | Path, output_zip: str | Path) -> Path:
        return build_export_bundle(legacy_path, output_zip)

    def import_legacy_atomic(self, legacy_path: str | Path, *, import_credentials: bool = True, overwrite_credentials: bool = False):
        self.target_db.parent.mkdir(parents=True, exist_ok=True)
        temp = self.target_db.with_name(self.target_db.name + ".migration.tmp")
        temp.unlink(missing_ok=True)
        temp_store = V2Store(temp)
        report = import_legacy_data(legacy_path, temp_store)
        if report.warnings:
            # Warnings are reported to the operator but do not necessarily mean data loss.
            pass

        backup: Path | None = None
        if self.target_db.exists():
            backup_dir = self.target_db.parent / "migration_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / (self.target_db.name + "." + now_iso().replace(":", "-") + ".bak")
            shutil.copy2(self.target_db, backup)
        os.replace(temp, self.target_db)

        credentials_message = "Credentials не переносилися."
        if import_credentials:
            ok, credentials_message = import_legacy_secrets(legacy_path, overwrite=overwrite_credentials)
            if not ok and "вже є credentials" not in credentials_message:
                report.warnings.append(credentials_message)
        return report, backup, credentials_message
