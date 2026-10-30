"""2.2.61: narrow official syndication recovery for an operator-known commercial RSS.

This is NOT generic anti-403 evasion. Syndicated publisher RSS is listed as
working by two independent reader catalogs (Feeder and Inoreader, 30 Oct 2026).
No network call on startup. Real operator-network yield needs LIVE confirmation.

Change exactly one enabled operator-known source which is CURRENTLY cooled due
to HTTP_403. No new source, deleting articles, replacing custom URLs, bypassing
a 403 on the original host or overriding other source cooldowns.
"""
from __future__ import annotations

import json
from typing import Any

from .loghub import event
from .storage import now_iso

OLD_URL = "https://design-milk.com/feed/"
PUBLIC_SYNDICATED_RSS = "https://feeds.feedburner.com/design-milk"
SOURCE_NAME = "Design Milk"
MARKER = "commercial_feed_recovery_261"


def recover_commercial_feed_261(store: Any) -> dict[str, Any]:
    """Migrate exact old Design Milk RSS to its public syndicated RSS only on 403.

    Reusing source.id is intentional: existing original-source dedupe, article
    FK, delivery receipts and canonical article URLs survive unchanged.
    """
    changes: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute(
            """SELECT s.id,s.channel_id,s.url,s.kind,s.enabled,s.initialized,
                      s.legacy_config_json,h.last_outcome
               FROM sources s
               JOIN channels c ON c.id=s.channel_id
               JOIN source_health h ON h.source_id=s.id
               WHERE c.editorial_runtime_profile='commercial_editorial'
                 AND s.name=? AND s.url=? AND s.kind='rss' AND s.enabled=1
                 AND h.last_outcome='HTTP_403'""",
            (SOURCE_NAME, OLD_URL),
        ).fetchall()
        for row in rows:
            sid = int(row["id"])
            channel_id = int(row["channel_id"])
            # Stop if operator already subscribed to same syndicated feed:
            # never merge identities or alter hand-added source rows.
            conflict = con.execute(
                "SELECT id FROM sources WHERE channel_id=? AND url=? AND id<>?",
                (channel_id, PUBLIC_SYNDICATED_RSS, sid),
            ).fetchone()
            if conflict:
                changes.append({"source_id": sid, "status": "existing_feed_conflict_no_change"})
                continue
            try:
                settings = json.loads(str(row["legacy_config_json"] or "{}"))
            except (TypeError, ValueError):
                settings = {}
            if not isinstance(settings, dict):
                settings = {}
            if MARKER in settings:
                changes.append({"source_id": sid, "status": "already_marked_no_change"})
                continue
            settings[MARKER] = {
                "previous_url": OLD_URL,
                "syndicated_url": PUBLIC_SYNDICATED_RSS,
                "reader_catalog_verified": True,
                "operator_network_verified": False,
                "reason": "old RSS HTTP 403; independent RSS readers verify a public syndicated feed",
            }
            # Keep initialized/priority/channel/FK/source id; do not import old
            # missing feed items. Strict source date + restart fence stay active.
            con.execute(
                """UPDATE sources
                   SET url=?,last_error='',last_checked_at='',
                       legacy_config_json=?
                   WHERE id=? AND url=?""",
                (PUBLIC_SYNDICATED_RSS, json.dumps(settings, ensure_ascii=False), sid, OLD_URL),
            )
            # Only the 403 state tied to the OLD URL is obsolete. Preserve
            # historical success_count/failure_count and all other sources.
            con.execute(
                """UPDATE source_health
                   SET consecutive_failures=0,cooldown_until='',
                       last_outcome='FEED_MIGRATED_261',last_error='',
                       zero_result_streak=0,slow_streak=0,
                       last_duration_ms=0,last_items=0,last_added=0,updated_at=?
                   WHERE source_id=? AND last_outcome='HTTP_403'""",
                (now_iso(), sid),
            )
            changes.append({"source_id": sid,"channel_id":channel_id,
                            "status":"syndicated_feed_migrated",
                            "previous_url":OLD_URL,"new_url":PUBLIC_SYNDICATED_RSS,
                            "operator_network_verified":False,
                            "history_preserved":True})
        con.commit()
    result={"version":"2.2.61","changed":sum(x["status"]=="syndicated_feed_migrated" for x in changes),
            "sources":changes,"operator_network_verified":False}
    event("ingest","official public syndicated RSS recovery 2.2.61",**result)
    return result
