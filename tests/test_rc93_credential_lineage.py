from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import telegram_autopilot.v2.credential_recovery as recovery
from telegram_autopilot.secrets_store import SecretConfig, _AAD, _HEADER


def _write_pair(data: Path, cfg: SecretConfig) -> None:
    data.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    nonce = os.urandom(12)
    plain = json.dumps(asdict(cfg.normalized()), ensure_ascii=False, sort_keys=True).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, plain, _AAD)
    (data / "secrets.key").write_bytes(key)
    (data / "secrets.secure").write_bytes(_HEADER + nonce + encrypted)


def test_selected_newer_rc_recovers_fallback_credentials_from_older_sibling(tmp_path: Path, monkeypatch) -> None:
    history = tmp_path / "history"
    selected_data = history / "UA_FREE_Telegram_Autopilot_v2.0.0-rc92_Windows_Portable" / "Data"
    older_data = history / "UA_FREE_Telegram_Autopilot_v2.0.0-rc84_Windows_Portable" / "Data"

    # Reproduce the live failure: the selected newer RC has a good DB/Codex state
    # but its encrypted pair no longer contains the older fallback-provider keys.
    _write_pair(selected_data, SecretConfig(codex_enabled=True))
    _write_pair(
        older_data,
        SecretConfig(
            gemini_api_key="gemini-old",
            nvidia_api_key="nvidia-old",
            groq_api_key="groq-old",
            cloudflare_account_id="cf-account",
            cloudflare_api_token="cf-token",
            default_telegram_bot_token="bot-old",
        ),
    )

    # Put the new portable somewhere else so recovery cannot accidentally pass by
    # finding the historical folders beside the current executable.
    current_root = tmp_path / "new-place" / "UA_FREE_Telegram_Autopilot_v2.0.0-rc93_Windows_Portable"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)
    current = SecretConfig(codex_enabled=True, groq_api_key="groq-current")
    saved: list[SecretConfig] = []

    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: current)
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.append(cfg))

    result = recovery.merge_missing_credentials_from_data(selected_data)

    assert result["merged"] is True
    assert saved
    merged = saved[-1]
    assert merged.codex_enabled is True
    assert merged.groq_api_key == "groq-current"  # current value always wins
    assert merged.gemini_api_key == "gemini-old"
    assert merged.nvidia_api_key == "nvidia-old"
    assert merged.cloudflare_account_id == "cf-account"
    assert merged.cloudflare_api_token == "cf-token"
    assert merged.default_telegram_bot_token == "bot-old"
    assert result["ai_routes"] == {
        "gemini": True,
        "nvidia": True,
        "groq": True,
        "cloudflare": True,
        "codex": True,
        "local": False,
    }
    assert "groq_api_key" not in result["recovered_fields"]
    assert any("rc84" in source.casefold() for source in result["sources"])
