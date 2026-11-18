"""2.3.36: operator-confirmed retirement of the Bored Panda commercial feed.

Only the exact original source/channel URL is disabled. Preserve all article
history, queue/delivery receipts, operator custom sources and channel policy.
One-time migration marker means explicit later operator re-enable is respected.
"""
from __future__ import annotations

from typing import Any
from .loghub import event
from .storage import now_iso

MIGRATION_KEY = "editorial_source_retirement_236_bored_panda"
SOURCE_NAME = "Bored Panda"
SOURCE_URL = "https://www.boredpanda.com/feed/"


def disable_bored_panda_236(store: Any) -> dict[str, Any]:
    result = {"status": "not_found", "disabled": 0, "channel_id": 2}
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM meta WHERE key=?", (MIGRATION_KEY,)).fetchone():
            con.commit()
            return {"status": "already_applied", "disabled": 0}
        rows = con.execute(
            """SELECT s.id,s.channel_id FROM sources s
               JOIN channels c ON c.id=s.channel_id
               WHERE s.name=? AND s.url=? AND s.enabled=1
                 AND c.channel_mode='editorial'
                 AND c.editorial_runtime_profile='commercial_editorial'""",
            (SOURCE_NAME, SOURCE_URL),
        ).fetchall()
        disabled = 0
        for row in rows:
            con.execute("UPDATE sources SET enabled=0 WHERE id=? AND enabled=1",
                        (int(row["id"]),))
            disabled += int(con.execute("SELECT changes()").fetchone()[0])
        con.execute("INSERT INTO meta(key,value) VALUES(?,?)",
                    (MIGRATION_KEY, now_iso()))
        con.commit()
        result = {"status": "applied", "disabled": disabled,
                  "matching_rows": len(rows)}
    event("ingest", "2.3.36 owner-retired Bored Panda commercial source", **result)
    return result
