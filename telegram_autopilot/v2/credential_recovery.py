from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..paths import data_dir
from ..secrets_store import SecretConfig, load_secrets_from_files


_SECRET_FILES = ("secrets.key", "secrets.secure")


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


def merge_missing_credentials_from_data(source_data: str | Path) -> dict[str, object]:
    """Import the encrypted credential pair from the Data folder selected by the user.

    This is deliberately deterministic.  It never scans sibling builds, Desktop,
    Downloads or OneDrive, and it never combines secrets from multiple versions.
    The selected pair must decrypt successfully before anything in the current
    Data directory is replaced.

    The historical function name is kept temporarily as a compatibility surface
    for first_run_import; its behaviour is now a single-source atomic import.
    """
    source = Path(source_data).resolve()
    source_key = source / "secrets.key"
    source_secure = source / "secrets.secure"
    if not source_key.is_file() or not source_secure.is_file():
        return {
            "merged": False,
            "reason": "selected_credentials_missing",
            "source": str(source),
            "recovered_fields": [],
        }

    try:
        cfg = load_secrets_from_files(source_key, source_secure).normalized()
    except Exception as exc:
        return {
            "merged": False,
            "reason": "selected_credentials_unreadable",
            "source": str(source),
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "recovered_fields": [],
        }

    target = data_dir()
    target.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name in _SECRET_FILES:
            src = source / name
            tmp = target / f".{name}.import.tmp"
            shutil.copy2(src, tmp)
            staged.append((tmp, target / name))
        for tmp, dst in staged:
            os.replace(tmp, dst)
    finally:
        for tmp, _dst in staged:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    routes = _ai_routes(cfg)
    return {
        "merged": True,
        "reason": "selected_credentials_pair_imported",
        "source": str(source),
        "recovered_fields": list(_SECRET_FILES),
        "ai_routes": routes,
        "fallback_routes": sum(1 for name in ("gemini", "nvidia", "groq", "cloudflare") if routes.get(name)),
    }


def recover_missing_credentials_from_siblings() -> dict[str, object]:
    """Compatibility no-op.

    Automatic sibling credential discovery was intentionally removed.  Credential
    migration is allowed only from the exact Data folder selected during import.
    """
    return {
        "recovered": False,
        "reason": "automatic_sibling_recovery_disabled",
    }
