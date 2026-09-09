from __future__ import annotations

import sqlite3
from pathlib import Path

import telegram_autopilot.v2.legacy_credentials as legacy_credentials


def _empty_legacy_data(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    db = path / "telegram_autopilot.sqlite3"
    con = sqlite3.connect(db)
    con.close()
    (path / "secrets.key").write_bytes(b"legacy-key-bytes")
    (path / "secrets.secure").write_bytes(b"legacy-secure-bytes")
    return path


def test_legacy_credentials_use_two_distinct_temp_files_and_copy_exact_pair(tmp_path: Path, monkeypatch) -> None:
    legacy = _empty_legacy_data(tmp_path / "legacy" / "Data")
    target = tmp_path / "v2" / "Data"
    target.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(legacy_credentials, "secret_key_path", lambda: target / "secrets.key")
    monkeypatch.setattr(legacy_credentials, "secrets_path", lambda: target / "secrets.secure")
    monkeypatch.setattr(legacy_credentials, "data_dir", lambda: target)

    ok, message = legacy_credentials.import_legacy_secrets(legacy)

    assert ok is True
    assert "перенесено" in message
    assert (target / "secrets.key").read_bytes() == b"legacy-key-bytes"
    assert (target / "secrets.secure").read_bytes() == b"legacy-secure-bytes"
    assert not list(target.glob("*.migration.tmp"))


def test_existing_credentials_are_not_overwritten_without_explicit_flag(tmp_path: Path, monkeypatch) -> None:
    legacy = _empty_legacy_data(tmp_path / "legacy" / "Data")
    target = tmp_path / "v2" / "Data"
    target.mkdir(parents=True, exist_ok=True)
    (target / "secrets.key").write_bytes(b"current-key")
    (target / "secrets.secure").write_bytes(b"current-secure")

    monkeypatch.setattr(legacy_credentials, "secret_key_path", lambda: target / "secrets.key")
    monkeypatch.setattr(legacy_credentials, "secrets_path", lambda: target / "secrets.secure")
    monkeypatch.setattr(legacy_credentials, "data_dir", lambda: target)

    ok, message = legacy_credentials.import_legacy_secrets(legacy, overwrite=False)

    assert ok is False
    assert "вже є credentials" in message
    assert (target / "secrets.key").read_bytes() == b"current-key"
    assert (target / "secrets.secure").read_bytes() == b"current-secure"
