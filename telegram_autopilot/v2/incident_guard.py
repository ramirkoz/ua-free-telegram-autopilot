"""Conservative final-stage published-incident dedupe for short local news rewrites.

Only block thin Zaporizhzhia strike injury summaries within a 45-minute
window of a previously committed injury/strike post. Full official updates
with additional distinct facts are not reclassified as duplicates by this
guard; the normal detailed event dedupe still applies.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta


def _is_strike_injury(text: str) -> bool:
    low = str(text or "").casefold()
    return bool(
        re.search(r"поран|постраждал", low)
        and re.search(r"удар|атак|обстріл|ракет|дрон|каб", low)
    )


def _region(text: str) -> str:
    low = str(text or "").casefold()
    if "запорі" in low:
        return "zaporizhzhia"
    return ""


def recent_community_incident_duplicate(store, channel_id: int, article_id: int, article) -> int:
    if int(channel_id) != 3:
        return 0
    source_text = str(article["raw_text"] or "")
    final_text = str(article["final_text"] or "")
    title = str(article["title"] or "")
    if not _is_strike_injury(" ".join((source_text, title, final_text))):
        return 0
    # Thin rephrased headline-only stories are not a fresh incident update.
    if len(source_text.strip()) > 175:
        return 0
    try:
        published = []
        with store.connect() as con:
            published = con.execute(
                """SELECT article_id, title, raw_text, final_text, published_at
                   FROM published_event_ledger
                   WHERE channel_id=? AND article_id<>?
                   ORDER BY published_at DESC LIMIT 60""",
                (channel_id, article_id),
            ).fetchall()
        now = datetime.now().astimezone()
        current_region = _region(" ".join((title, source_text, final_text)))
        if not current_region:
            return 0
        for item in published:
            other_at = datetime.fromisoformat(str(item["published_at"]).replace("Z", "+00:00"))
            if not other_at.tzinfo:
                continue
            if not timedelta(0) <= (now - other_at.astimezone(now.tzinfo)) <= timedelta(minutes=45):
                continue
            other = " ".join((str(item["title"] or ""), str(item["raw_text"] or ""), str(item["final_text"] or "")))
            if not _is_strike_injury(other) or _region(other) != current_region:
                continue
            return int(item["article_id"])
    except (ValueError, TypeError, KeyError):
        return 0
    return 0
