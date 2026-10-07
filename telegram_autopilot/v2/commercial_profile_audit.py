from __future__ import annotations

import json
from typing import Any

from .domain import EditorialRuntimeProfile


_CANONICAL_THRESHOLD_KEYS = {
    "broad_interest_fit",
    "broad_interest_score",
    "broad_general_interest",
    "broad_retellability",
    "broad_culture_or_surprise",
    "commercial_case_score",
    "commercial_transferability",
    "commercial_anchor",
    "creative_case_score",
    "mechanism_case_score",
}


def audit_commercial_profiles(store) -> dict[str, Any]:
    """Non-mutating RC104 audit for commercial_editorial channels.

    ProductVault defines this profile as broad-audience/visual/shareable,
    media-first capable and operator-configurable. RC104 therefore audits
    persisted settings but never silently rewrites operator policy at startup.
    """
    results: list[dict[str, Any]] = []
    issue_total = 0
    with store.connect() as con:
        rows = con.execute(
            """SELECT c.id,c.name,c.media_first_allowed,c.media_min_text_chars,
                      c.editorial_thresholds_json,
                      p.media_policy,p.selection_rules,p.rejection_rules
                 FROM channels c JOIN channel_policies p ON p.channel_id=c.id
                WHERE c.editorial_runtime_profile=?
                ORDER BY c.id""",
            (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
        ).fetchall()

    for row in rows:
        issues: list[str] = []
        notes: list[str] = []
        try:
            thresholds = json.loads(str(row["editorial_thresholds_json"] or "{}"))
        except Exception:
            thresholds = {}
        if not isinstance(thresholds, dict):
            thresholds = {}

        missing_thresholds = sorted(_CANONICAL_THRESHOLD_KEYS.difference(thresholds))
        if not bool(int(row["media_first_allowed"] or 0)):
            issues.append("media_first_disabled")
        if int(row["media_min_text_chars"] or 0) > 120:
            notes.append("media_first_text_threshold_above_rc98_reference")
        if missing_thresholds:
            notes.append("missing_broad_audience_thresholds:" + ",".join(missing_thresholds))

        selection = str(row["selection_rules"] or "")
        rejection = str(row["rejection_rules"] or "")
        if "BROAD_AUDIENCE" not in selection:
            notes.append("broad_audience_selection_marker_absent")
        if "BROAD_AUDIENCE" not in rejection:
            notes.append("broad_audience_rejection_marker_absent")

        configured_media_policy = str(row["media_policy"] or "").strip().lower()
        if configured_media_policy not in {"required", "preferred", "optional"}:
            issues.append("invalid_media_policy")
        media_policy = configured_media_policy if configured_media_policy in {"required", "preferred", "optional"} else "optional"

        issue_total += len(issues)
        results.append({
            "channel_id": int(row["id"]),
            "channel_name": str(row["name"] or ""),
            "status": "needs_attention" if issues else "ok",
            "issues": issues,
            "notes": notes,
            "media_first_allowed": bool(int(row["media_first_allowed"] or 0)),
            "media_min_text_chars": int(row["media_min_text_chars"] or 0),
            "media_policy": media_policy,
            "configured_media_policy": configured_media_policy,
            "missing_thresholds": missing_thresholds,
        })

    return {
        "schema": "ua-free-autopilot-commercial-profile-audit-v1",
        "mode": "non_mutating",
        "channels": len(results),
        "issues": issue_total,
        "healthy": issue_total == 0,
        "results": results,
    }
