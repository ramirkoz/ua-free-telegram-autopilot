"""Bounded, read-only audit for monitoring media carried in separate Telegram posts.

Evidence is not ownership. A nearby photo/video without a verified reply, album
or explicit source media URL must never be attached automatically.
"""
from __future__ import annotations

import json
from typing import Any, Iterable


def summarize_monitoring_media_provenance(
    rows: Iterable[Any], *, sample_limit: int = 6
) -> dict[str, Any]:
    """Expose source-post diagnostics without changing publication eligibility."""
    affected = 0
    candidates = 0
    verified_split = 0
    examples: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        try:
            layout = json.loads(str(row["article_layout_json"] or "{}"))
        except (KeyError, TypeError, ValueError):
            continue
        telegram = layout.get("telegram") if isinstance(layout, dict) else None
        if not isinstance(telegram, dict):
            continue
        records = telegram.get("source_message_records_v1")
        if (bool(telegram.get("stitched")) and isinstance(records, list) and
                len({str(item.get("post")) for item in records if isinstance(item, dict)}) > 1):
            verified_split += 1
        unresolved = telegram.get("unresolved_nearby_media_v1")
        if not isinstance(unresolved, list) or not unresolved:
            continue
        try:
            article_id = int(row["id"])
            source_url = str(row["source_url"] or "")[:240]
        except (KeyError, TypeError, ValueError):
            continue
        # One text article can have several nearby media-only posts; count
        # each distinct candidate once per article, not each metadata alias.
        distinct = []
        for item in unresolved:
            if not isinstance(item, dict):
                continue
            post = str(item.get("post") or "")
            if not post or (source_url, post) in seen:
                continue
            seen.add((source_url, post))
            distinct.append(item)
        if not distinct:
            continue
        affected += 1
        candidates += len(distinct)
        if len(examples) >= max(0, sample_limit):
            continue
        item = distinct[0]
        try:
            media_count = max(0, int(item.get("media_count") or 0))
        except (ValueError, TypeError):
            media_count = 0
        examples.append({
            "article_id": article_id,
            "source_url": source_url,
            "nearby_post": str(item.get("post") or "")[:120],
            "media_count": media_count,
            "video_seen": bool(item.get("video_seen")),
            "seconds_apart": item.get("seconds_apart"),
            "reason": "UNVERIFIED_NEARBY_MEDIA_NOT_ATTACHED",
        })
    return {
        "scope": "monitoring_diagnostic_only",
        "unverified_articles_60m": affected,
        "unverified_candidates_60m": candidates,
        "verified_split_articles_60m": verified_split,
        "sample": examples,
        "ownership_inferred_from_proximity": False,
    }
