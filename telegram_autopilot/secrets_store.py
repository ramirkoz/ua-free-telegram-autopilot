from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .paths import secret_key_path, secrets_path

_HEADER = b"UA_FREE_TELEGRAM_AUTOPILOT_AESGCM_V1\n"
_AAD = b"UA_FREE_TELEGRAM_AUTOPILOT_SECRETS_V1"


@dataclass(slots=True)
class SecretConfig:
    default_telegram_bot_token: str = ""
    channel_bot_tokens: dict[str, str] = field(default_factory=dict)
    gemini_api_key: str = ""
    nvidia_api_key: str = ""
    groq_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    codex_enabled: bool = False
    local_enabled: bool = False
    local_base_url: str = "http://127.0.0.1:8080/v1"
    local_model: str = "local-model"
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_user_session: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_account_email: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_user_access_token: str = ""
    facebook_graph_version: str = "v26.0"
    facebook_pages: list[dict[str, str]] = field(default_factory=list)

    def normalized(self) -> "SecretConfig":
        try:
            telegram_api_id = max(0, int(self.telegram_api_id or 0))
        except (TypeError, ValueError):
            telegram_api_id = 0
        return SecretConfig(
            default_telegram_bot_token=self.default_telegram_bot_token.strip(),
            channel_bot_tokens={str(k): str(v).strip() for k, v in self.channel_bot_tokens.items() if str(v).strip()},
            gemini_api_key=self.gemini_api_key.strip(),
            nvidia_api_key=self.nvidia_api_key.strip(),
            groq_api_key=self.groq_api_key.strip(),
            cloudflare_account_id=self.cloudflare_account_id.strip(),
            cloudflare_api_token=self.cloudflare_api_token.strip(),
            codex_enabled=bool(self.codex_enabled),
            local_enabled=bool(self.local_enabled),
            local_base_url=self.local_base_url.strip() or "http://127.0.0.1:8080/v1",
            local_model=self.local_model.strip() or "local-model",
            telegram_api_id=telegram_api_id,
            telegram_api_hash=str(self.telegram_api_hash or "").strip(),
            telegram_phone=str(self.telegram_phone or "").strip(),
            telegram_user_session=str(self.telegram_user_session or "").strip(),
            google_client_id=str(self.google_client_id or "").strip(),
            google_client_secret=str(self.google_client_secret or "").strip(),
            google_refresh_token=str(self.google_refresh_token or "").strip(),
            google_account_email=str(self.google_account_email or "").strip(),
            facebook_app_id=str(self.facebook_app_id or "").strip(),
            facebook_app_secret=str(self.facebook_app_secret or "").strip(),
            facebook_user_access_token=str(self.facebook_user_access_token or "").strip(),
            facebook_graph_version=(str(self.facebook_graph_version or "v26.0").strip() or "v26.0"),
            facebook_pages=[
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or item.get("id") or "").strip(),
                    "access_token": str(item.get("access_token") or "").strip(),
                }
                for item in (self.facebook_pages or [])
                if isinstance(item, dict) and str(item.get("id") or "").strip() and str(item.get("access_token") or "").strip()
            ],
        )


def _load_or_create_key() -> bytes:
    path = secret_key_path()
    if path.exists():
        raw = path.read_bytes()
        if len(raw) != 32:
            raise RuntimeError("Файл ключа секретів пошкоджено.")
        return raw
    raw = secrets.token_bytes(32)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(raw)
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)
    return raw


def load_secrets_from_files(key_path, secure_path) -> SecretConfig:
    key_file = os.fspath(key_path)
    secure_file = os.fspath(secure_path)
    key = open(key_file, "rb").read()
    if len(key) != 32:
        raise RuntimeError("Файл ключа секретів пошкоджено.")
    raw = open(secure_file, "rb").read()
    if not raw.startswith(_HEADER):
        raise RuntimeError("Файл секретів має неправильний формат.")
    payload = raw[len(_HEADER):]
    if len(payload) < 13:
        raise RuntimeError("Файл секретів пошкоджено.")
    nonce, ciphertext = payload[:12], payload[12:]
    plain = AESGCM(key).decrypt(nonce, ciphertext, _AAD)
    data = json.loads(plain.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Файл секретів має неправильний формат.")
    allowed = set(SecretConfig.__dataclass_fields__)
    return SecretConfig(**{k: data[k] for k in data if k in allowed}).normalized()


def load_secrets() -> SecretConfig:
    path = secrets_path()
    if not path.exists():
        return SecretConfig()
    key_path = secret_key_path()
    if not key_path.exists():
        _load_or_create_key()
    return load_secrets_from_files(key_path, path)


def save_secrets(value: SecretConfig) -> None:
    cfg = value.normalized()
    plain = json.dumps(asdict(cfg), ensure_ascii=False, sort_keys=True).encode("utf-8")
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_load_or_create_key()).encrypt(nonce, plain, _AAD)
    target = secrets_path()
    temp = target.with_suffix(".tmp")
    temp.write_bytes(_HEADER + nonce + encrypted)
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(target)
