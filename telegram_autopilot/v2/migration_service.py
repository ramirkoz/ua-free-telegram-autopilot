from __future__ import annotations

import gc
import os
import sqlite3
import tempfile
from pathlib import Path

from .legacy_credentials import import_legacy_secrets
from .migration import build_export_bundle, import_legacy_data, locate_legacy_database
from .storage import V2Store, now_iso


_STABLE_V2_TABLES = (
    "channels",
    "channel_policies",
    "sources",
    "articles",
    "feedback",
    "feedback_editor_reactions",
)


def _table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [str(row[1]) for row in con.execute(f'PRAGMA table_info("{table}")')]
    except sqlite3.Error:
        return []


def _copy_compatible_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> int:
    src_cols = _table_columns(src, table)
    dst_cols = set(_table_columns(dst, table))
    cols = [name for name in src_cols if name in dst_cols]
    if not cols:
        return 0
    quoted = ",".join('"' + name.replace('"', '""') + '"' for name in cols)
    marks = ",".join("?" for _ in cols)
    rows = src.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
    if not rows:
        return 0
    dst.executemany(f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({marks})', [tuple(row) for row in rows])
    return len(rows)


def _looks_like_current_v2(db: Path) -> bool:
    con = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True, timeout=15)
    try:
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {"channels", "channel_policies", "sources", "articles"}.issubset(tables)
    finally:
        con.close()


class MigrationManager:
    """Read-only legacy import with a Windows-safe SQLite handoff.

    V2 is a running GUI process and may have short-lived read handles open on the
    destination database. Windows therefore cannot reliably replace the database
    file with ``os.replace`` while the application is alive. The migration is
    built in an isolated temporary SQLite database, validated, backed up, then
    copied into the live database through SQLite's own online-backup API. This
    keeps the operation inside SQLite's locking model and avoids WinError 32.
    """

    def __init__(self, target_db: str | Path):
        self.target_db = Path(target_db)

    def export_legacy(self, legacy_path: str | Path, output_zip: str | Path) -> Path:
        return build_export_bundle(legacy_path, output_zip)

    @staticmethod
    def _sqlite_backup(source: Path, destination: Path) -> None:
        """Copy one SQLite database into another using SQLite locking, not rename."""
        source = Path(source)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
        dst = sqlite3.connect(destination, timeout=30)
        try:
            src.execute("PRAGMA busy_timeout=30000")
            dst.execute("PRAGMA busy_timeout=30000")
            src.backup(dst, pages=512, sleep=0.05)
            dst.commit()
        finally:
            try:
                dst.close()
            finally:
                src.close()

    @staticmethod
    def _validate_database(path: Path) -> None:
        con = sqlite3.connect(path, timeout=30)
        try:
            con.execute("PRAGMA busy_timeout=30000")
            row = con.execute("PRAGMA quick_check").fetchone()
            if not row or str(row[0]).casefold() != "ok":
                raise RuntimeError(f"V2 migration database failed quick_check: {row!r}")
            required = {"channels", "channel_policies", "sources", "articles", "jobs"}
            existing = {str(r[0]) for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(required - existing)
            if missing:
                raise RuntimeError("V2 migration database is missing tables: " + ", ".join(missing))
        finally:
            con.close()

    def import_clean_portable(
        self,
        old_data: str | Path,
        *,
        import_credentials: bool = True,
        overwrite_credentials: bool = False,
    ) -> tuple[dict[str, int], Path | None, str]:
        """Build a fresh V2 database from durable user/editorial data only.

        Runtime queues, provider cooldowns, worker leases, source-health cooldowns,
        audit noise and old Tools are deliberately not copied.  This is the
        first-run migration path for a newly unpacked portable release.
        """
        source_db = locate_legacy_database(old_data)
        if not _looks_like_current_v2(source_db):
            report, backup, cred = self.import_legacy_atomic(
                old_data,
                import_credentials=import_credentials,
                overwrite_credentials=overwrite_credentials,
            )
            return {
                "channels": int(getattr(report, "channels_imported", 0) or 0),
                "sources": int(getattr(report, "sources_imported", 0) or 0),
                "articles": int(getattr(report, "articles_imported", 0) or 0),
                "feedback": int(getattr(report, "feedback_imported", 0) or 0),
            }, backup, cred

        self.target_db.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=self.target_db.name + ".clean-import.",
            suffix=".tmp.sqlite3",
            dir=self.target_db.parent,
        )
        os.close(fd)
        temp = Path(temp_name)
        temp.unlink(missing_ok=True)
        backup: Path | None = None
        summary: dict[str, int] = {}
        try:
            # Creating the store establishes only the current clean schema.
            temp_store = V2Store(temp)
            del temp_store
            src = sqlite3.connect(f"file:{source_db.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
            src.row_factory = sqlite3.Row
            dst = sqlite3.connect(temp, timeout=30)
            try:
                src.execute("PRAGMA query_only=ON")
                dst.execute("PRAGMA foreign_keys=OFF")
                dst.execute("BEGIN IMMEDIATE")
                # Empty schema is expected, but DELETE makes the function safely repeatable.
                for table in reversed(_STABLE_V2_TABLES):
                    if _table_columns(dst, table):
                        dst.execute(f'DELETE FROM "{table}"')
                for table in _STABLE_V2_TABLES:
                    if _table_columns(src, table) and _table_columns(dst, table):
                        summary[table] = _copy_compatible_table(src, dst, table)
                dst.commit()
                dst.execute("PRAGMA foreign_keys=ON")
            except Exception:
                dst.rollback()
                raise
            finally:
                dst.close()
                src.close()
            self._validate_database(temp)

            if self.target_db.exists():
                backup_dir = self.target_db.parent / "migration_backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / (
                    self.target_db.name + "." + now_iso().replace(":", "-") + ".bak.sqlite3"
                )
                self._sqlite_backup(self.target_db, backup)
            self._sqlite_backup(temp, self.target_db)
            self._validate_database(self.target_db)

            credentials_message = "Credentials не переносилися."
            if import_credentials:
                ok, credentials_message = import_legacy_secrets(
                    old_data, overwrite=overwrite_credentials
                )
                if not ok and "вже є credentials" not in credentials_message:
                    credentials_message = credentials_message
            return summary, backup, credentials_message
        except Exception:
            if backup is not None and backup.exists():
                try:
                    self._sqlite_backup(backup, self.target_db)
                except Exception:
                    pass
            raise
        finally:
            gc.collect()
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def import_legacy_atomic(
        self,
        legacy_path: str | Path,
        *,
        import_credentials: bool = True,
        overwrite_credentials: bool = False,
    ):
        self.target_db.parent.mkdir(parents=True, exist_ok=True)

        # Use a unique temporary database. A stale/locked temp from a previous
        # interrupted Windows run can therefore never block the next attempt.
        fd, temp_name = tempfile.mkstemp(
            prefix=self.target_db.name + ".migration.",
            suffix=".tmp.sqlite3",
            dir=self.target_db.parent,
        )
        os.close(fd)
        temp = Path(temp_name)
        temp.unlink(missing_ok=True)

        backup: Path | None = None
        try:
            temp_store = V2Store(temp)
            report = import_legacy_data(legacy_path, temp_store)
            self._validate_database(temp)

            if self.target_db.exists():
                backup_dir = self.target_db.parent / "migration_backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / (
                    self.target_db.name
                    + "."
                    + now_iso().replace(":", "-")
                    + ".bak.sqlite3"
                )
                self._sqlite_backup(self.target_db, backup)
                self._validate_database(backup)

            # Crucial Windows fix: do not rename/replace a live SQLite file.
            # SQLite backup waits for its own locks and safely rewrites destination.
            self._sqlite_backup(temp, self.target_db)
            self._validate_database(self.target_db)

            credentials_message = "Credentials не переносилися."
            if import_credentials:
                try:
                    ok, credentials_message = import_legacy_secrets(
                        legacy_path, overwrite=overwrite_credentials
                    )
                    if not ok and "вже є credentials" not in credentials_message:
                        report.warnings.append(credentials_message)
                except Exception as exc:
                    # Credentials are independent from the migrated SQLite data.
                    # A filesystem/permission problem must not roll back channels,
                    # sources, policies and history that were already validated.
                    credentials_message = (
                        "Credentials не перенесено: "
                        + f"{type(exc).__name__}: {exc}"
                    )
                    report.warnings.append(credentials_message)
            return report, backup, credentials_message
        except Exception:
            # If the destination database copy failed after a backup was created,
            # restore the previous V2 database through SQLite. Credential failures
            # are handled above and intentionally do not enter this rollback path.
            if backup is not None and backup.exists():
                try:
                    self._sqlite_backup(backup, self.target_db)
                except Exception:
                    pass
            raise
        finally:
            # sqlite3 connection objects created inside migration functions are
            # normally released immediately on CPython; collect defensively before
            # trying to remove the temp on Windows. A leftover unique temp is safe.
            gc.collect()
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
