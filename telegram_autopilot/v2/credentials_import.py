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


def import_credentials_from_data(source_data: str | Path) -> dict[str, object]:
    """Import one validated encrypted credential pair from the selected Data folder.

    No sibling discovery or cross-version merging is allowed. The exact pair chosen
    by the operator must decrypt successfully before either target file is replaced.
    """
    source = Path(source_data).resolve()
    source_key = source / "secrets.key"
    source_secure = source / "secrets.secure"
    if not source_key.is_file() or not source_secure.is_file():
        return {
            "imported": False,
            "reason": "credentials_missing",
            "source": str(source),
            "ai_routes": {},
        }

    try:
        cfg = load_secrets_from_files(source_key, source_secure).normalized()
    except Exception as exc:
        return {
            "imported": False,
            "reason": "credentials_unreadable",
            "source": str(source),
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "ai_routes": {},
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
        "imported": True,
        "reason": "credentials_imported",
        "source": str(source),
        "ai_routes": routes,
        "fallback_routes": sum(
            1 for name in ("gemini", "nvidia", "groq", "cloudflare") if routes.get(name)
        ),
    }
