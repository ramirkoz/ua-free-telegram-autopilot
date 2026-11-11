"""v2.3.23: repair two science sources whose stored address yields nothing usable.

Evidence, 11.11.2026, the project's own collector on the operator's Windows
machine plus the operator SQLite snapshot of 10.11 (0 articles from either
source in the last 7 days):

* Quanta Magazine  - the stored feed returns one item dated 2013.
                     https://www.quantamagazine.org/feed/ returns 5 dated items,
                     2 in 72 h, full text, media 5/5.
* The Conversation - the stored regional page returns 8 items, none with a
                     verifiable publication time, so all fail the source-date
                     fence. The technology Atom feed returns 25 dated items,
                     2 in 72 h, full text.

Idempotent, exact name+URL only: a row the operator edited is left alone. The
source id, history, priority and enabled flag are kept. The row is marked
uninitialised so the feed's existing items are recorded as known and nothing
from the backlog is published.
"""
from __future__ import annotations

import json
from typing import Any

from .loghub import event
from .storage import now_iso

KEY = "source_url_repairs_2323_once"
REPAIRS: tuple[tuple[str, str, str], ...] = (
    ("Quanta Magazine", "https://www.quantamagazine.org/quanta/feed/",
     "https://www.quantamagazine.org/feed/"),
    ("The Conversation", "https://theconversation.com/europe",
     "https://theconversation.com/global/technology/articles.atom"),
)


def apply_source_url_repairs_2323(store: Any) -> dict[str, Any]:
    repaired: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM meta WHERE key=?", (KEY,)).fetchone():
            con.commit()
            return {"version": "2.3.23", "status": "already_applied", "repaired": []}
        for name, old_url, new_url in REPAIRS:
            rows = con.execute(
                "SELECT id,channel_id FROM sources WHERE name=? AND url=?", (name, old_url)
            ).fetchall()
            for row in rows:
                sid, cid = int(row["id"]), int(row["channel_id"])
                if con.execute(
                    "SELECT 1 FROM sources WHERE channel_id=? AND url=?", (cid, new_url)
                ).fetchone():
                    continue  # the operator already has the working address
                con.execute(
                    "UPDATE sources SET url=?,kind='rss',initialized=0 WHERE id=?",
                    (new_url, sid),
                )
                repaired.append({"source_id": sid, "channel_id": cid, "source_name": name,
                                 "old_url": old_url, "new_url": new_url})
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?)",
            (KEY, json.dumps({"timestamp": now_iso(), "repaired": repaired}, ensure_ascii=False)),
        )
        con.commit()
    for row in repaired:
        event("ingest", "2.3.23 source address repaired", **row)
    return {"version": "2.3.23", "status": "applied", "repaired": repaired}
