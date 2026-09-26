from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import telegram_autopilot.v2.credential_recovery as recovery
from telegram_autopilot.secrets_store import SecretConfig, _AAD, _HEADER
from telegram_autopilot.v2.migration_repair import repair_polling_baseline
from telegram_autopilot.v2.storage import V2Store, now_iso


def _write_pair(data: Path, cfg: SecretConfig) -> None:
    import json
    from dataclasses import asdict

    data.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    nonce = os.urandom(12)
    plain = json.dumps(asdict(cfg.normalized()), ensure_ascii=False, sort_keys=True).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, plain, _AAD)
    (data / "secrets.key").write_bytes(key)
    (data / "secrets.secure").write_bytes(_HEADER + nonce + encrypted)


def test_rc90_codex_does_not_block_recovery_of_missing_api_providers(tmp_path: Path, monkeypatch) -> None:
    current_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc89_Windows_Portable"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)

    donor_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc85_Windows_Portable"
    _write_pair(
        donor_root / "Data",
        SecretConfig(
            gemini_api_key="gemini-old",
            nvidia_api_key="nvidia-old",
            groq_api_key="groq-old",
            cloudflare_account_id="cf-account",
            cloudflare_api_token="cf-token",
        ),
    )

    current_cfg = SecretConfig(codex_enabled=True, groq_api_key="groq-current")
    saved: list[SecretConfig] = []
    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: current_cfg)
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.recover_missing_credentials_from_siblings()

    assert result["recovered"] is True
    assert saved
    merged = saved[-1]
    assert merged.codex_enabled is True
    assert merged.groq_api_key == "groq-current"
    assert merged.gemini_api_key == "gemini-old"
    assert merged.nvidia_api_key == "nvidia-old"
    assert merged.cloudflare_account_id == "cf-account"
    assert merged.cloudflare_api_token == "cf-token"
    assert "gemini_api_key" in result["recovered_fields"]
    assert "groq_api_key" not in result["recovered_fields"]
    assert (current_data / "rc90_credential_recovery.json").is_file()


def test_rc90_can_merge_missing_values_from_more_than_one_valid_sibling(tmp_path: Path, monkeypatch) -> None:
    current_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc89"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)

    _write_pair(
        tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc84" / "Data",
        SecretConfig(gemini_api_key="gemini", default_telegram_bot_token="bot"),
    )
    _write_pair(
        tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc85" / "Data",
        SecretConfig(nvidia_api_key="nvidia", cloudflare_account_id="acc", cloudflare_api_token="tok"),
    )

    saved: list[SecretConfig] = []
    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: SecretConfig(codex_enabled=True))
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.recover_missing_credentials_from_siblings()
    merged = saved[-1]
    assert result["recovered"] is True
    assert len(result["sources"]) == 2
    assert merged.gemini_api_key == "gemini"
    assert merged.nvidia_api_key == "nvidia"
    assert merged.cloudflare_account_id == "acc"
    assert merged.cloudflare_api_token == "tok"
    assert merged.default_telegram_bot_token == "bot"


def test_rc90_recovery_is_noop_when_siblings_add_nothing(tmp_path: Path, monkeypatch) -> None:
    current_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc89"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)
    cfg = SecretConfig(codex_enabled=True, gemini_api_key="same")
    _write_pair(tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc85" / "Data", cfg)
    saved: list[SecretConfig] = []

    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: cfg)
    monkeypatch.setattr(recovery, "save_secrets", lambda value: saved.append(value))

    result = recovery.recover_missing_credentials_from_siblings()
    assert result["recovered"] is False
    assert result["reason"] == "no_missing_values_found"
    assert saved == []


def test_rc90_poll_marker_is_not_consumed_on_empty_schema(tmp_path: Path) -> None:
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    store = V2Store(db)

    first = repair_polling_baseline(store)
    assert first == {"repaired": False, "reason": "no_channels", "channels_changed": 0}
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT value FROM meta WHERE key='rc90_poll_interval_15m_repair_v1'").fetchone() is None

    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,poll_interval_minutes,created_at,updated_at)
               VALUES(1,'Imported','@imported',1,'editorial',5,?,?)""",
            (stamp, stamp),
        )

    second = repair_polling_baseline(store)
    assert second["repaired"] is True
    assert second["channels_changed"] == 1
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 15
        assert con.execute("SELECT value FROM meta WHERE key='rc90_poll_interval_15m_repair_v1'").fetchone()[0] == "1"


def test_rc90_repairs_existing_rc89_five_minute_rows_once_then_respects_operator(tmp_path: Path) -> None:
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    store = V2Store(db)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,poll_interval_minutes,created_at,updated_at)
               VALUES(1,'A','@a',1,'editorial',5,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            "INSERT INTO meta(key,value) VALUES('rc89_poll_interval_15m_repair_v1','1') ON CONFLICT(key) DO UPDATE SET value='1'"
        )

    result = repair_polling_baseline(store)
    assert result["repaired"] is True
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 15
        con.execute("UPDATE channels SET poll_interval_minutes=7 WHERE id=1")
        con.commit()

    again = repair_polling_baseline(store)
    assert again["reason"] == "already_applied"
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 7


def test_rc90_selected_import_merges_credentials_without_overwriting_current(tmp_path: Path, monkeypatch) -> None:
    donor_data = tmp_path / "old" / "Data"
    _write_pair(
        donor_data,
        SecretConfig(
            gemini_api_key="gemini-old",
            nvidia_api_key="nvidia-old",
            groq_api_key="groq-old",
            default_telegram_bot_token="bot-old",
        ),
    )
    current = SecretConfig(codex_enabled=True, groq_api_key="groq-current")
    saved: list[SecretConfig] = []
    monkeypatch.setattr(recovery, "load_secrets", lambda: current)
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.merge_missing_credentials_from_data(donor_data)

    assert result["merged"] is True
    assert saved
    merged = saved[-1]
    assert merged.codex_enabled is True
    assert merged.groq_api_key == "groq-current"
    assert merged.gemini_api_key == "gemini-old"
    assert merged.nvidia_api_key == "nvidia-old"
    assert merged.default_telegram_bot_token == "bot-old"
    assert "groq_api_key" not in result["recovered_fields"]


def test_rc90_recovery_fails_closed_when_current_secret_pair_is_unreadable(tmp_path: Path, monkeypatch) -> None:
    current_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc89"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)
    saved: list[SecretConfig] = []
    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: (_ for _ in ()).throw(RuntimeError("bad secret pair")))
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.recover_missing_credentials_from_siblings()

    assert result["recovered"] is False
    assert result["reason"] == "current_credentials_unreadable"
    assert saved == []
