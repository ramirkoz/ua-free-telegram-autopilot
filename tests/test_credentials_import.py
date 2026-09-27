from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import telegram_autopilot.v2.credentials_import as credentials_import
from telegram_autopilot.secrets_store import SecretConfig, _AAD, _HEADER, load_secrets_from_files


def _write_pair(data: Path, cfg: SecretConfig) -> None:
    data.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    nonce = os.urandom(12)
    plain = json.dumps(asdict(cfg.normalized()), ensure_ascii=False, sort_keys=True).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, plain, _AAD)
    (data / "secrets.key").write_bytes(key)
    (data / "secrets.secure").write_bytes(_HEADER + nonce + encrypted)


def test_import_uses_only_selected_valid_pair(tmp_path: Path, monkeypatch) -> None:
    selected = tmp_path / "selected" / "Data"
    target = tmp_path / "current" / "Data"
    cfg = SecretConfig(
        gemini_api_key="gemini-test",
        nvidia_api_key="nvidia-test",
        groq_api_key="groq-test",
        cloudflare_account_id="account-test",
        cloudflare_api_token="token-test",
        codex_enabled=True,
    )
    _write_pair(selected, cfg)
    monkeypatch.setattr(credentials_import, "data_dir", lambda: target)

    result = credentials_import.import_credentials_from_data(selected)

    assert result["imported"] is True
    assert result["fallback_routes"] == 4
    imported = load_secrets_from_files(target / "secrets.key", target / "secrets.secure")
    assert imported.gemini_api_key == "gemini-test"
    assert imported.nvidia_api_key == "nvidia-test"
    assert imported.groq_api_key == "groq-test"
    assert imported.cloudflare_account_id == "account-test"
    assert imported.cloudflare_api_token == "token-test"
    assert imported.codex_enabled is True


def test_missing_selected_pair_does_not_touch_current_credentials(tmp_path: Path, monkeypatch) -> None:
    selected = tmp_path / "selected" / "Data"
    selected.mkdir(parents=True)
    target = tmp_path / "current" / "Data"
    target.mkdir(parents=True)
    current_key = b"k" * 32
    current_secure = b"current-encrypted-value"
    (target / "secrets.key").write_bytes(current_key)
    (target / "secrets.secure").write_bytes(current_secure)
    monkeypatch.setattr(credentials_import, "data_dir", lambda: target)

    result = credentials_import.import_credentials_from_data(selected)

    assert result["imported"] is False
    assert result["reason"] == "credentials_missing"
    assert (target / "secrets.key").read_bytes() == current_key
    assert (target / "secrets.secure").read_bytes() == current_secure


def test_unreadable_selected_pair_does_not_touch_current_credentials(tmp_path: Path, monkeypatch) -> None:
    selected = tmp_path / "selected" / "Data"
    selected.mkdir(parents=True)
    (selected / "secrets.key").write_bytes(b"x" * 32)
    (selected / "secrets.secure").write_bytes(b"not-a-valid-secret-payload")
    target = tmp_path / "current" / "Data"
    target.mkdir(parents=True)
    (target / "secrets.key").write_bytes(b"k" * 32)
    (target / "secrets.secure").write_bytes(b"keep-me")
    monkeypatch.setattr(credentials_import, "data_dir", lambda: target)

    result = credentials_import.import_credentials_from_data(selected)

    assert result["imported"] is False
    assert result["reason"] == "credentials_unreadable"
    assert (target / "secrets.key").read_bytes() == b"k" * 32
    assert (target / "secrets.secure").read_bytes() == b"keep-me"
