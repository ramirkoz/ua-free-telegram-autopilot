"""Windows-specific atomic encrypted-secrets replacement regressions."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_autopilot import secrets_store


def _windows_permission_error(code=5):
    exc = PermissionError(13, "Access denied")
    exc.winerror = code
    return exc


def test_transient_windows_lock_retries_without_losing_secrets(tmp_path, monkeypatch):
    target = tmp_path / "secrets.secure"
    target.write_bytes(b"old-encrypted")
    calls = []
    real_replace = os.replace
    def replace(src, dst):
        calls.append((src, dst))
        if len(calls) == 1:
            raise _windows_permission_error()
        return real_replace(src, dst)
    fake_os = SimpleNamespace(
        name="nt", replace=replace, chmod=os.chmod,
        fsync=os.fsync, unlink=os.unlink,
    )
    monkeypatch.setattr(secrets_store, "os", fake_os)
    monkeypatch.setattr(secrets_store.time, "sleep", lambda _: None)
    secrets_store._atomic_secret_write(target, b"new-encrypted")
    assert target.read_bytes() == b"new-encrypted"
    assert len(calls) == 2
    assert sorted(x.name for x in tmp_path.iterdir()) == ["secrets.secure"]


def test_permanent_access_denied_keeps_prior_encrypted_file(tmp_path, monkeypatch):
    target = tmp_path / "secrets.secure"
    target.write_bytes(b"old-encrypted")
    def deny(src, dst):
        raise _windows_permission_error()
    fake_os = SimpleNamespace(
        name="nt", replace=deny, chmod=os.chmod,
        fsync=os.fsync, unlink=os.unlink,
    )
    monkeypatch.setattr(secrets_store, "os", fake_os)
    monkeypatch.setattr(secrets_store.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        secrets_store._atomic_secret_write(target, b"new-encrypted")
    assert target.read_bytes() == b"old-encrypted"
    assert sorted(x.name for x in tmp_path.iterdir()) == ["secrets.secure"]


def test_regular_atomic_write_creates_new_secrets(tmp_path):
    target = tmp_path / "secrets.secure"
    secrets_store._atomic_secret_write(target, b"encrypted-content")
    assert target.read_bytes() == b"encrypted-content"
    assert len(list(tmp_path.iterdir())) == 1
