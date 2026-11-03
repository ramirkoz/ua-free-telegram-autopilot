"""2.3.6: repair verified v2.3.5 Trend Hunter / Design Milk relay collision.

Only the 2.3.5 operator migration *recorded* skip is eligible; this does
not re-enable arbitrary manually disabled sources and never changes IDs,
article history, channel settings or delivery receipts.
"""
from __future__ import annotations
import json
from typing import Any
from .loghub import event
from .storage import now_iso

MARKER = "commercial_feedburner_236_channel_"
NAME = "Trend Hunter"
OLD_URL = "https://www.trendhunter.com/"
RSS_URL = "http://feeds.feedburner.com/TrendHunter/Top10"


def restore_trend_hunter_236(store: Any) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute(
            """SELECT s.id,s.channel_id,s.name,s.url,s.kind,s.enabled,
                      s.legacy_config_json
               FROM sources s JOIN channels c ON c.id=s.channel_id
               WHERE c.channel_mode='editorial'
                 AND c.editorial_runtime_profile='commercial_editorial'
                 AND s.name=?""", (NAME,),
        ).fetchall()
        for r in rows:
            cid, sid = int(r["channel_id"]), int(r["id"])
            key = MARKER + str(cid)
            if con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone():
                continue
            # The broken 2.3.5 attempt must be recorded by this exact channel.
            prior = con.execute(
                "SELECT value FROM meta WHERE key=?",
                ("commercial_sources_235_once_channel_" + str(cid),),
            ).fetchone()
            try:
                report = json.loads(prior[0]) if prior else {}
            except (TypeError, ValueError):
                report = {}
            skipped = report.get("skipped", []) if isinstance(report, dict) else []
            bug_confirmed = any(
                isinstance(item, dict) and item.get("name") == NAME
                and item.get("reason") == "feed_host_in_use" for item in skipped
            )
            if not bug_confirmed or str(r["url"] or "") != OLD_URL or str(r["kind"] or "") != "page" or int(r["enabled"] or 0) != 0:
                continue
            collision = con.execute(
                "SELECT 1 FROM sources WHERE channel_id=? AND url=? AND id<>?",
                (cid, RSS_URL, sid),
            ).fetchone()
            if collision:
                continue
            try:
                extra = json.loads(str(r["legacy_config_json"] or "{}"))
            except (TypeError, ValueError):
                extra = {}
            if not isinstance(extra, dict):
                extra = {}
            extra["commercial_feedburner_236"] = {
                "old_url": OLD_URL, "new_url": RSS_URL,
                "reason": "2.3.5 incorrectly equated Trend Hunter and Design Milk relay hosts",
                "operator_network_verified": False,
            }
            con.execute(
                """UPDATE sources SET url=?,kind='rss',enabled=1,initialized=0,
                   last_checked_at='',last_error='',legacy_config_json=?
                   WHERE id=? AND name=? AND url=? AND kind='page' AND enabled=0""",
                (RSS_URL, json.dumps(extra, ensure_ascii=False), sid, NAME, OLD_URL),
            )
            if not int(con.execute("SELECT changes()").fetchone()[0]):
                continue
            con.execute(
                """UPDATE source_health SET consecutive_failures=0,
                   cooldown_until='',last_outcome='TREND_HUNTER_RESTORED_236',
                   last_error='',zero_result_streak=0,slow_streak=0,
                   last_duration_ms=0,last_items=0,last_added=0,updated_at=?
                   WHERE source_id=?""", (now_iso(), sid),
            )
            report2 = {"channel_id": cid, "source_id": sid,
                       "outcome": "restored", "publisher": NAME,
                       "history_preserved": True}
            con.execute("INSERT INTO meta(key,value) VALUES(?,?)",
                        (key, json.dumps(report2, ensure_ascii=False)))
            changes.append(report2)
        con.commit()
    for report in changes:
        event("ingest", "Trend Hunter 2.3.5 feed host regression repaired", **report)
    return {"version": "2.3.6", "restored": len(changes), "changes": changes}
