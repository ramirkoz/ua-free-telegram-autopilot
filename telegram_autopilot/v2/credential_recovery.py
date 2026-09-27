from __future__ import annotations

from pathlib import Path

from .credentials_import import import_credentials_from_data


def merge_missing_credentials_from_data(source_data: str | Path) -> dict[str, object]:
    """Compatibility adapter for the first-run importer.

    The implementation is a single-source encrypted-pair import. No sibling search
    or multi-version credential merging exists in the active runtime.
    """
    result = import_credentials_from_data(source_data)
    return {
        "merged": bool(result.get("imported")),
        "reason": str(result.get("reason") or ""),
        "source": str(result.get("source") or source_data),
        "recovered_fields": ["secrets.key", "secrets.secure"] if result.get("imported") else [],
        "ai_routes": dict(result.get("ai_routes") or {}),
        "fallback_routes": int(result.get("fallback_routes") or 0),
        **({"error": result["error"]} if result.get("error") else {}),
    }
