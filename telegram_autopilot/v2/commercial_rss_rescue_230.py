"""2.3.0: Restore verified publisher-owned RSS for two zero-yield commercial pages.

Only existing, enabled commercial PAGE sources with exact operator URLs and
observed zero-yield state are eligible. No network activity during startup;
no addition of sources, no changes to source history or publication policy.
The operator's own network must verify RSS availability after installation.
"""
from __future__ import annotations

import json
from typing import Any

from .loghub import event
from .storage import now_iso

MARKER = "commercial_rss_rescue_230"
RECOVERY = (
    ("Adweek", "https://www.adweek.com/", "https://www.adweek.com/feed/"),
    ("Fast Company", "https://www.fastcompany.com/", "https://www.fastcompany.com/co-design/rss"),
)


def recover_commercial_rss_230(store: Any) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        for name, old_url, rss_url in RECOVERY:
            rows = con.execute(
                """SELECT s.id,s.channel_id,s.legacy_config_json,h.last_outcome
                   FROM sources s
                   JOIN channels c ON c.id=s.channel_id
                   JOIN source_health h ON h.source_id=s.id
                   WHERE c.editorial_runtime_profile='commercial_editorial'
                     AND s.name=? AND s.url=? AND s.kind='page' AND s.enabled=1
                     AND h.last_outcome IN ('KNOWN_ONLY','EMPTY','SLOW_EMPTY')
                     AND COALESCE(h.last_added,0)=0""",
                (name, old_url),
            ).fetchall()
            for row in rows:
                sid, cid = int(row["id"]), int(row["channel_id"])
                if con.execute(
                    "SELECT id FROM sources WHERE channel_id=? AND url=? AND id<>?",
                    (cid, rss_url, sid),
                ).fetchone() is not None:
                    changes.append({"source_id": sid, "name": name, "outcome": "collision_no_change"})
                    continue
                try:
                    settings = json.loads(str(row["legacy_config_json"] or "{}"))
                except (TypeError, ValueError):
                    settings = {}
                if not isinstance(settings, dict):
                    settings = {}
                if MARKER in settings:
                    changes.append({"source_id": sid, "name": name, "outcome": "already_marked"})
                    continue
                settings[MARKER] = {
                    "previous_url": old_url,
                    "publisher_rss": rss_url,
                    "previous_outcome": str(row["last_outcome"]),
                    "independent_feed_reader_verified": True,
                    "operator_network_verified": False,
                    "no_backlog_replay": True,
                }
                con.execute(
                    """UPDATE sources SET kind='rss',url=?,last_checked_at='',
                              last_error='',legacy_config_json=?
                       WHERE id=? AND url=? AND kind='page'""",
                    (rss_url, json.dumps(settings, ensure_ascii=False), sid, old_url),
                )
                con.execute(
                    """UPDATE source_health
                       SET consecutive_failures=0,cooldown_until='',
                           last_outcome='RSS_MIGRATED_230',last_error='',
                           zero_result_streak=0,slow_streak=0,
                           last_duration_ms=0,last_items=0,last_added=0,updated_at=?
                       WHERE source_id=? AND last_outcome=?""",
                    (now_iso(), sid, str(row["last_outcome"])),
                )
                changes.append({"source_id": sid, "channel_id": cid,
                                "name": name, "outcome": "migrated", "new_url": rss_url})
        con.commit()
    report = {
        "version": "2.3.0", "changed": sum(x["outcome"] == "migrated" for x in changes),
        "sources": changes, "operator_network_verified": False,
        "no_new_sources": True, "no_operator_policy_change": True,
    }
    event("ingest", "2.3.0 verified commercial RSS recovery", **report)
    return report
