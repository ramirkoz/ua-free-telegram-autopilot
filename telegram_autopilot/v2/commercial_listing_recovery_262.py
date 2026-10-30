"""2.2.62: publisher-owned commercial listing repair; strictly observed failures.

Only existing operator known sources with exact old URLs, enabled commercial
profile, kind=page AND their specific persisted failing outcome are eligible.
Other channels/custom sources, source identity/FKs, operator cadence, article
history, delivery receipts, and all unrelated cooldowns remain untouched.
Publisher listing endpoints verified on their own public websites. Ad Age
/news/ is publicly indexed by Feeder but operator access remains unverified.
"""
from __future__ import annotations

import json
from typing import Any

from .loghub import event
from .storage import now_iso

MARKER = "commercial_listing_recovery_262"
# One source per publisher: preserve article attribution and existing article
# identities rather than create duplicate sources. No feed mirror/403 bypass.
RECOVERY: tuple[tuple[str, str, str, str, int], ...] = (
    ("Shots", "https://shots.net/", "https://shots.net/the-work", "TIMEOUT", 2),
    ("Ad Age", "https://adage.com/", "https://adage.com/news/", "SLOW_EMPTY", 2),
    ("Famous Campaigns", "https://www.famouscampaigns.com/",
     "https://www.famouscampaigns.com/2026/", "EMPTY", 4),
)


def recover_commercial_listings_262(store: Any) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        for name, old, new, failing_outcome, fetch_cap in RECOVERY:
            rows = con.execute(
                """SELECT s.id,s.channel_id,s.kind,s.url,s.name,s.enabled,
                          s.legacy_config_json,h.last_outcome
                   FROM sources s
                   JOIN channels c ON c.id=s.channel_id
                   JOIN source_health h ON h.source_id=s.id
                   WHERE c.editorial_runtime_profile='commercial_editorial'
                     AND s.kind='page' AND s.name=? AND s.url=?
                     AND s.enabled=1 AND h.last_outcome=?""",
                (name, old, failing_outcome),
            ).fetchall()
            for row in rows:
                sid = int(row["id"])
                cid = int(row["channel_id"])
                collision = con.execute(
                    "SELECT id FROM sources WHERE channel_id=? AND url=? AND id<>?",
                    (cid, new, sid),
                ).fetchone()
                if collision is not None:
                    changes.append({"source_id": sid, "name": name, "outcome": "collision_preserved"})
                    continue
                try:
                    config = json.loads(str(row["legacy_config_json"] or "{}"))
                except (ValueError, TypeError):
                    config = {}
                if not isinstance(config, dict):
                    config = {}
                if MARKER in config:
                    changes.append({"source_id": sid, "name": name, "outcome": "previously_marked"})
                    continue
                config[MARKER] = {
                    "previous_url": old, "listing_url": new,
                    "previous_outcome": failing_outcome,
                    "max_article_page_hydrations_per_cycle": fetch_cap,
                    "operator_live_yield_confirmed": False,
                    "publisher_page_only": True,
                    "requires_source_published_time": True,
                    "no_backlog_replay": True,
                }
                con.execute(
                    """UPDATE sources SET url=?,last_error='',last_checked_at='',
                              legacy_config_json=?
                       WHERE id=? AND url=?""",
                    (new, json.dumps(config, ensure_ascii=False), sid, old),
                )
                # Clear ONLY the health status attached to the previous URL.
                # Counters and unrelated cooldowns remain as historical evidence.
                con.execute(
                    """UPDATE source_health SET consecutive_failures=0,
                              cooldown_until='',last_outcome='LISTING_MIGRATED_262',
                              last_error='',zero_result_streak=0,slow_streak=0,
                              last_duration_ms=0,last_items=0,last_added=0,updated_at=?
                       WHERE source_id=? AND last_outcome=?""",
                    (now_iso(), sid, failing_outcome),
                )
                changes.append({"source_id": sid, "name": name, "outcome": "listing_migrated",
                                "new_url": new, "fetch_cap": fetch_cap})
        con.commit()
    result = {"version": "2.2.62",
              "changed": sum(x["outcome"] == "listing_migrated" for x in changes),
              "sources": changes, "operator_live_yield_confirmed": False}
    event("ingest", "2.2.62 commercial original-publisher listing repair", **result)
    return result
