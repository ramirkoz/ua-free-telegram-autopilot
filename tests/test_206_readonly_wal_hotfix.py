from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from telegram_autopilot.v2.migration_service import MigrationManager


def test_readonly_wal_uses_private_writable_snapshot(tmp_path: Path, monkeypatch):
    source = tmp_path / "old" / "original.sqlite3"
    source.parent.mkdir()
    dest = tmp_path / "new" / "restored.sqlite3"
    owner = sqlite3.connect(source)
    owner.execute("PRAGMA journal_mode=WAL")
    owner.execute("CREATE TABLE facts(text TEXT)")
    owner.execute("INSERT INTO facts VALUES ('preserved')")
    owner.commit()
    assert Path(str(source) + "-wal").exists()
    original_connect = sqlite3.connect

    def readonly_source_fails(db_path, *args, **kwargs):
        if isinstance(db_path, str) and "mode=ro" in db_path and "old/" in db_path:
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return original_connect(db_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", readonly_source_fails)
    try:
        MigrationManager._sqlite_backup(source, dest)
    finally:
        owner.close()
    with original_connect(dest) as connection:
        assert connection.execute("SELECT text FROM facts").fetchone()[0] == "preserved"


def test_non_wal_readonly_error_fails_safely(tmp_path: Path, monkeypatch):
    source = tmp_path / "original.sqlite3"
    dest = tmp_path / "output.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE facts(text TEXT)")
    original_connect = sqlite3.connect

    def readonly_fails(db_path, *args, **kwargs):
        if isinstance(db_path, str) and "mode=ro" in db_path:
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return original_connect(db_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", readonly_fails)
    with pytest.raises(RuntimeError, match="no WAL fallback"):
        MigrationManager._sqlite_backup(source, dest)
