from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from ..paths import data_dir, runtime_dir
from ..secrets_store import SecretConfig, load_secrets, load_secrets_from_files, save_secrets
from .storage import now_iso

_MARKER = "rc90_credential_recovery.json"


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


def _autopilot_data_dirs(parent: Path, *, exclude_root: Path | None = None) -> Iterable[Path]:
    try:
        roots = [
            item
            for item in parent.iterdir()
            if item.is_dir()
            and (exclude_root is None or item.resolve() != exclude_root.resolve())
            and item.name.casefold().startswith("ua_free_telegram_autopilot")
        ]
    except OSError:
        roots = []
    for root in roots:
        data = root / "Data"
        if data.is_dir():
            yield data.resolve()


def _candidate_data_dirs() -> Iterable[Path]:
    current_root = runtime_dir().resolve()
    yield from _autopilot_data_dirs(current_root.parent, exclude_root=current_root)


def _lineage_data_dirs(source_data: str | Path) -> Iterable[Path]:
    """Yield credential donors around both the selected old build and current build.

    A migration may be selected from a newer RC whose database is good but whose
    secret pair already lost older fallback providers. In that case the authoritative
    donor can be an older Autopilot folder beside the selected build, not beside the
    new portable. Only explicit Autopilot sibling folders are inspected; there is no
    recursive home-directory secret scan.
    """
    source = Path(source_data).resolve()
    seen: set[str] = set()

    def emit(path: Path):
        try:
            resolved = path.resolve()
        except OSError:
            return
        key = str(resolved).casefold()
        if key in seen or not resolved.is_dir():
            return
        seen.add(key)
        yield resolved

    yield from emit(source)

    # source is normally <old portable>/Data, so source.parent.parent is the
    # directory that contains RC84/RC90/RC91/... sibling portable folders.
    old_root = source.parent
    old_parent = old_root.parent
    for candidate in _autopilot_data_dirs(old_parent):
        yield from emit(candidate)

    # Preserve the RC90 behaviour too: donors located beside the new portable.
    for candidate in _candidate_data_dirs():
        yield from emit(candidate)


def _merge_missing(current: SecretConfig, donor: SecretConfig) -> SecretConfig:
    """Fill only empty values. Existing current credentials always win."""
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

    donor_pages = {str(item.get("id") or "").strip(): dict(item) for item in (donor.facebook_pages or []) if str(item.get("id") or "").strip()}
    current_pages = {str(item.get("id") or "").strip(): dict(item) for item in (current.facebook_pages or []) if str(item.get("id") or "").strip()}
    donor_pages.update(current_pages)
    payload["facebook_pages"] = list(donor_pages.values())

    return SecretConfig(**payload).normalized()


def _changed_fields(before: SecretConfig, after: SecretConfig) -> list[str]:
    left = asdict(before.normalized())
    right = asdict(after.normalized())
    return sorted(key for key in right if left.get(key) != right.get(key))


def _ai_routes(cfg: SecretConfig) -> dict[str, bool]:
    value = cfg.normalized()
    return {
        "gemini": bool(value.gemini_api_key),
        "nvidia": bool(value.nvidia_api_key),
        "groq": bool(value.groq_api_key),
        "cloudflare": bool(value.cloudflare_account_id and value.cloudflare_api_token),
        "codex": bool(value.codex_enabled),
        "local": bool(value.local_enabled),
    }


def _validated_candidates(paths: Iterable[Path]) -> list[tuple[int, float, Path, SecretConfig]]:
    candidates: list[tuple[int, float, Path, SecretConfig]] = []
    for source_data in paths:
        key = source_data / "secrets.key"
        secure = source_data / "secrets.secure"
        if not key.is_file() or not secure.is_file():
            continue
        try:
            cfg = load_secrets_from_files(key, secure).normalized()
        except Exception:
            continue
        score = _candidate_score(cfg)
        if score <= 0:
            continue
        try:
            mtime = max(key.stat().st_mtime, secure.stat().st_mtime)
        except OSError:
            mtime = 0.0
        candidates.append((score, mtime, source_data, cfg))
    return candidates


def _merge_candidates(current: SecretConfig, candidates: list[tuple[int, float, Path, SecretConfig]]) -> tuple[SecretConfig, list[str], set[str]]:
    merged = current
    used_sources: list[str] = []
    recovered_fields: set[str] = set()
    for _score, _mtime, source_data, donor in sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True):
        before = merged
        after = _merge_missing(before, donor)
        changed = _changed_fields(before, after)
        if changed:
            merged = after
            recovered_fields.update(changed)
            used_sources.append(str(source_data))
    return merged, used_sources, recovered_fields


def merge_missing_credentials_from_data(source_data: str | Path) -> dict[str, object]:
    """Recover missing credentials from the selected migration lineage.

    Existing current values always win. The selected Data is checked first as a
    lineage anchor, then sibling Autopilot Data folders around that old build and
    around the new portable are considered. This repairs chains where a newer RC
    preserved the database but had already lost one or more fallback-provider keys.
    """
    try:
        current = load_secrets().normalized()
    except Exception as exc:
        return {
            "merged": False,
            "reason": "current_credentials_unreadable",
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "recovered_fields": [],
        }

    candidates = _validated_candidates(_lineage_data_dirs(source_data))
    if not candidates:
        return {
            "merged": False,
            "reason": "no_valid_lineage_credentials",
            "recovered_fields": [],
            "ai_routes": _ai_routes(current),
        }

    merged, used_sources, recovered_fields = _merge_candidates(current, candidates)
    if not recovered_fields:
        return {
            "merged": False,
            "reason": "no_missing_values_found",
            "sources_checked": len(candidates),
            "recovered_fields": [],
            "ai_routes": _ai_routes(current),
        }

    save_secrets(merged)
    return {
        "merged": True,
        "reason": "missing_values_merged_from_lineage",
        "sources": used_sources,
        "sources_checked": len(candidates),
        "recovered_fields": sorted(recovered_fields),
        "ai_routes": _ai_routes(merged),
    }


def recover_missing_credentials_from_siblings() -> dict[str, object]:
    """Recover missing credentials from validated sibling Autopilot Data folders."""
    target = data_dir()
    marker = target / _MARKER
    try:
        current = load_secrets().normalized()
    except Exception as exc:
        return {
            "recovered": False,
            "reason": "current_credentials_unreadable",
            "detail": f"{type(exc).__name__}: {exc}"[:500],
        }

    candidates = _validated_candidates(_candidate_data_dirs())
    if not candidates:
        return {
            "recovered": False,
            "reason": "no_valid_sibling_credentials",
            "ai_routes": _ai_routes(current),
        }

    merged, used_sources, recovered_fields = _merge_candidates(current, candidates)
    if not recovered_fields:
        return {
            "recovered": False,
            "reason": "no_missing_values_found",
            "candidates": len(candidates),
            "ai_routes": _ai_routes(current),
        }

    save_secrets(merged)
    payload = {
        "recovered": True,
        "sources": used_sources,
        "candidates": len(candidates),
        "recovered_fields": sorted(recovered_fields),
        "at": now_iso(),
        "ai_routes": _ai_routes(merged),
    }
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
