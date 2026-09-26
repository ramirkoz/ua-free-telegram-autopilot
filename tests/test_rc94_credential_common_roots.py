from pathlib import Path

from telegram_autopilot.secrets_store import SecretConfig
from telegram_autopilot.v2 import credential_recovery as recovery


def test_rc94_recovers_fallback_ai_credentials_from_common_portable_roots(tmp_path, monkeypatch):
    user = tmp_path / "user"
    desktop = user / "Desktop"
    downloads = user / "Downloads"
    desktop.mkdir(parents=True)
    downloads.mkdir(parents=True)

    current_root = downloads / "UA_FREE_Telegram_Autopilot_v2.0.0-rc94_Windows_Portable"
    current_data = current_root / "Data"
    current_data.mkdir(parents=True)

    old_data = desktop / "UA_FREE_Telegram_Autopilot_v2.0.0-rc84_Windows_Portable" / "Data"
    old_data.mkdir(parents=True)
    (old_data / "secrets.key").write_bytes(b"k" * 32)
    (old_data / "secrets.secure").write_bytes(b"encrypted")

    monkeypatch.setenv("USERPROFILE", str(user))
    monkeypatch.setattr(recovery, "runtime_dir", lambda: current_root)
    monkeypatch.setattr(recovery, "data_dir", lambda: current_data)
    monkeypatch.setattr(recovery, "load_secrets", lambda: SecretConfig(codex_enabled=True))

    donor = SecretConfig(
        gemini_api_key="gemini",
        nvidia_api_key="nvidia",
        groq_api_key="groq",
        cloudflare_account_id="account",
        cloudflare_api_token="token",
    )

    def fake_load_pair(key_path, secure_path):
        assert Path(key_path).parent == old_data
        assert Path(secure_path).parent == old_data
        return donor

    saved = {}
    monkeypatch.setattr(recovery, "load_secrets_from_files", fake_load_pair)
    monkeypatch.setattr(recovery, "save_secrets", lambda cfg: saved.setdefault("cfg", cfg))

    result = recovery.recover_missing_credentials_from_siblings()

    assert result["recovered"] is True
    assert result["fallback_routes"] == 4
    assert str(old_data) in result["sources"]
    restored = saved["cfg"]
    assert restored.codex_enabled is True
    assert restored.gemini_api_key == "gemini"
    assert restored.nvidia_api_key == "nvidia"
    assert restored.groq_api_key == "groq"
    assert restored.cloudflare_account_id == "account"
    assert restored.cloudflare_api_token == "token"
