from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import telegram_autopilot.v2.credential_recovery as recovery
from telegram_autopilot.secrets_store import SecretConfig, _AAD, _HEADER
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


def test_rc89_recovers_missing_ai_fields_without_overwriting_current_secrets(tmp_path: Path, monkeypatch) -> None:
    current_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc88_Windows_Portable_MANUAL_TEST"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)

    donor_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc85_Windows_Portable_MANUAL_TEST"
    donor_cfg = SecretConfig(
        gemini_api_key="gemini-old",
        nvidia_api_key="nvidia-old",
        groq_api_key="groq-old",
        cloudflare_account_id="cf-account",
        cloudflare_api_token="cf-token",
        default_telegram_bot_token="bot-old",
        google_client_id="google-old",
    )
    _write_pair(donor_root / "Data", donor_cfg)

    current_cfg = SecretConfig(
        google_client_id="google-current",
        google_client_secret="secret-current",
        google_refresh_token="refresh-current",
    )
    saved: list[SecretConfig] = []

    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: current_cfg)
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.recover_missing_credentials_from_siblings()

    assert result["recovered"] is True
    assert saved
    merged = saved[-1]
    assert merged.gemini_api_key == "gemini-old"
    assert merged.nvidia_api_key == "nvidia-old"
    assert merged.groq_api_key == "groq-old"
    assert merged.cloudflare_account_id == "cf-account"
    assert merged.cloudflare_api_token == "cf-token"
    assert merged.default_telegram_bot_token == "bot-old"
    assert merged.google_client_id == "google-current"
    assert merged.google_client_secret == "secret-current"
    assert merged.google_refresh_token == "refresh-current"
    assert (current_data / "rc89_credential_recovery.json").is_file()


def test_rc89_does_not_touch_config_when_ai_already_present(tmp_path: Path, monkeypatch) -> None:
    current_root = tmp_path / "UA_FREE_Telegram_Autopilot_v2.0.0-rc88"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)
    saved: list[SecretConfig] = []

    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: SecretConfig(groq_api_key="already"))
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.recover_missing_credentials_from_siblings()

    assert result == {"recovered": False, "reason": "ai_already_configured"}
    assert saved == []


def test_rc89_repairs_carried_forward_five_minute_polling_once(tmp_path: Path) -> None:
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    store = V2Store(db)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,poll_interval_minutes,created_at,updated_at)
               VALUES(1,'A','@a',1,'editorial',15,?,?)""",
            (stamp, stamp),
        )
        con.execute("UPDATE channels SET poll_interval_minutes=5 WHERE id=1")
        con.execute("DELETE FROM meta WHERE key='rc89_poll_interval_15m_repair_v1'")

    V2Store(db)
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 15
        assert con.execute("SELECT value FROM meta WHERE key='rc89_poll_interval_15m_repair_v1'").fetchone()[0] == "1"

    # After the one repair pass, an operator may deliberately choose another value.
    with sqlite3.connect(db) as con:
        con.execute("UPDATE channels SET poll_interval_minutes=7 WHERE id=1")
        con.commit()
    V2Store(db)
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 7
