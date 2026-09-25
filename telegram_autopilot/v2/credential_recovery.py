from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from ..paths import data_dir, runtime_dir
from ..secrets_store import SecretConfig, load_secrets, load_secrets_from_files, save_secrets
from .storage import now_iso

_MARKER = "rc89_credential_recovery.json"


def _ai_configured(cfg: SecretConfig) -> bool:
    return bool(
        cfg.gemini_api_key
        or cfg.nvidia_api_key
        or cfg.groq_api_key
        or (cfg.cloudflare_account_id and cfg.cloudflare_api_token)
        or cfg.codex_enabled
        or cfg.local_enabled
    )


def _candidate_score(cfg: SecretConfig) -> int:
    score = 0
    score += 20 if cfg.gemini_api_key else 0
    score += 20 if cfg.nvidia_api_key else 0
    score += 20 if cfg.groq_api_key else 0
    score += 20 if (cfg.cloudflare_account_id and cfg.cloudflare_api_token) else 0
    score += 5 if cfg.codex_enabled else 0
    score += 5 if cfg.local_enabled else 0
    score += 8 if cfg.default_telegram_bot_token else 0
    score += min(8, len(cfg.channel_bot_tokens or {}))
    score += 5 if (cfg.telegram_api_id and cfg.telegram_api_hash) else 0
    score += 3 if cfg.telegram_user_session else 0
    score += 4 if (cfg.google_client_id and cfg.google_client_secret and cfg.google_refresh_token) else 0
    score += 3 if cfg.facebook_user_access_token else 0
    return score


def _candidate_data_dirs() -> Iterable[Path]:
    current_root = runtime_dir().resolve()
    roots = []
    parent = current_root.parent
    try:
        roots.extend(
            item
            for item in parent.iterdir()
            if item.is_dir()
            and item.resolve() != current_root
            and item.name.casefold().startswith("ua_free_telegram_autopilot")
        )
    except OSError:
        pass
    for root in roots:
        data = root / "Data"
        if data.is_dir():
            yield data


def _merge_missing(current: SecretConfig, donor: SecretConfig) -> SecretConfig:
    payload = asdict(current)
    donor_payload = asdict(donor)

    scalar_fields = (
        "default_telegram_bot_token",
        "gemini_api_key",
        "nvidia_api_key",
        "groq_api_key",
        "cloudflare_account_id",
        "cloudflare_api_token",
        "telegram_api_hash",
        "telegram_phone",
        "telegram_user_session",
        "google_client_id",
        "google_client_secret",
        "google_refresh_token",
        "google_account_email",
        "facebook_app_id",
        "facebook_app_secret",
        "facebook_user_access_token",
    )
    for field in scalar_fields:
        if not str(payload.get(field) or "").strip() and str(donor_payload.get(field) or "").strip():
            payload[field] = donor_payload[field]

    if not int(payload.get("telegram_api_id") or 0) and int(donor_payload.get("telegram_api_id") or 0):
        payload["telegram_api_id"] = int(donor_payload["telegram_api_id"])

    if not bool(payload.get("codex_enabled")) and bool(donor_payload.get("codex_enabled")):
        payload["codex_enabled"] = True
    if not bool(payload.get("local_enabled")) and bool(donor_payload.get("local_enabled")):
        payload["local_enabled"] = True
        payload["local_base_url"] = donor_payload.get("local_base_url") or payload.get("local_base_url")
        payload["local_model"] = donor_payload.get("local_model") or payload.get("local_model")

    channel_tokens = dict(donor.channel_bot_tokens or {})
    channel_tokens.update(dict(current.channel_bot_tokens or {}))
    payload["channel_bot_tokens"] = channel_tokens

    if not list(current.facebook_pages or []) and list(donor.facebook_pages or []):
        payload["facebook_pages"] = list(donor.facebook_pages)

    return SecretConfig(**payload).normalized()


def recover_missing_credentials_from_siblings() -> dict[str, object]:
    """Recover only missing credentials from a validated older portable.

    RC88 could preserve the V2 database while leaving a newer Data folder with a
    partial secrets file.  We never overwrite non-empty current values.  Recovery
    runs only while no AI provider is configured and accepts only decryptable
    sibling secret pairs that contain at least one usable AI route.
    """
    target = data_dir()
    marker = target / _MARKER
    try:
        current = load_secrets()
    except Exception:
        current = SecretConfig()

    if _ai_configured(current):
        return {"recovered": False, "reason": "ai_already_configured"}

    candidates: list[tuple[int, float, Path, SecretConfig]] = []
    for source_data in _candidate_data_dirs():
        key = source_data / "secrets.key"
        secure = source_data / "secrets.secure"
        if not key.is_file() or not secure.is_file():
            continue
        try:
            cfg = load_secrets_from_files(key, secure)
        except Exception:
            continue
        if not _ai_configured(cfg):
            continue
        try:
            mtime = max(key.stat().st_mtime, secure.stat().st_mtime)
        except OSError:
            mtime = 0.0
        candidates.append((_candidate_score(cfg), mtime, source_data, cfg))

    if not candidates:
        return {"recovered": False, "reason": "no_valid_sibling_credentials"}

    score, _mtime, source_data, donor = max(candidates, key=lambda item: (item[0], item[1]))
    merged = _merge_missing(current, donor)
    if not _ai_configured(merged):
        return {"recovered": False, "reason": "candidate_merge_no_ai"}

    save_secrets(merged)
    payload = {
        "recovered": True,
        "source": str(source_data),
        "score": int(score),
        "at": now_iso(),
        "ai_routes": {
            "gemini": bool(merged.gemini_api_key),
            "nvidia": bool(merged.nvidia_api_key),
            "groq": bool(merged.groq_api_key),
            "cloudflare": bool(merged.cloudflare_account_id and merged.cloudflare_api_token),
            "codex": bool(merged.codex_enabled),
            "local": bool(merged.local_enabled),
        },
    }
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
