"""v2.3.23: retire three dead ПРОДАНО! inputs, add two measured working feeds.

Evidence, 11.11.2026, the project's own collector on the operator's Windows
machine (tools/probe_sources.py) plus the operator SQLite snapshot of 10.11:

* My Modern Met  - HTTP 403 on every fetch (LIVE 10.11 and probe 11.11).
* Trend Hunter   - feed returns 0 items; 0 articles in 72 h.
* Fast Company   - 20 items, none with a verifiable publication time, so every
                   item fails the source-date fence; 0 articles in 72 h.

* designboom - Art : 10 dated items, 4 in 24 h, median body 1 799 chars, media 10/10.
* The Awesomer     : 20 dated items, 9 in 24 h, media 20/20 (unusual objects).

Idempotent, exact name+URL, canonical commercial preset only. Rows are disabled,
never deleted; custom or edited rows and all history stay untouched. No backlog
is replayed: new sources start uninitialised, so their existing feed items are
recorded as known and only later items are considered.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .loghub import event
from .storage import now_iso

PREFIX = "commercial_sources_2323_once_channel_"
RETIRE_EXACT: dict[str, str] = {
    "My Modern Met": "https://mymodernmet.com/feed/",
    "Trend Hunter": "http://feeds.feedburner.com/TrendHunter/Top10",
    "Fast Company": "https://www.fastcompany.com/co-design/rss",
}
FRESH: tuple[tuple[str, str, int], ...] = (
    ("designboom — Art", "https://www.designboom.com/art/feed/", 17),
    ("The Awesomer", "https://theawesomer.com/feed/", 21),
)


def _identity(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return (parts.hostname or "").casefold().removeprefix("www.") + parts.path.rstrip("/").casefold()


def apply_commercial_sources_2323(store: Any) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        channels = con.execute(
            "SELECT id FROM channels WHERE channel_mode='editorial' "
            "AND editorial_runtime_profile='commercial_editorial'"
        ).fetchall()
        for ch in channels:
            cid = int(ch["id"])
            key = PREFIX + str(cid)
            if con.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone():
                reports.append({"channel_id": cid, "status": "already_applied"})
                continue
            rows = con.execute(
                "SELECT id,name,url,enabled FROM sources WHERE channel_id=?", (cid,)
            ).fetchall()
            # Only the canonical consumer portfolio installed by 2.3.22 is touched.
            if not con.execute(
                "SELECT 1 FROM meta WHERE key=?", ("commercial_sources_2322_once_channel_" + str(cid),)
            ).fetchone():
                reports.append({"channel_id": cid, "status": "custom_preserved"})
                continue
            retired, added = [], []
            for r in rows:
                name, url = str(r["name"]), str(r["url"])
                if RETIRE_EXACT.get(name) == url and int(r["enabled"]):
                    con.execute("UPDATE sources SET enabled=0 WHERE id=?", (int(r["id"]),))
                    retired.append(name)
            identities = {_identity(str(r["url"])) for r in rows}
            names = {str(r["name"]).casefold() for r in rows}
            for name, url, priority in FRESH:
                if _identity(url) in identities or name.casefold() in names:
                    continue
                info = json.dumps({"commercial_sources_2323": {
                    "introduced_in": "2.3.23",
                    "collector_probe_passed": "2026-11-11",
                    "do_not_replay_history": True,
                }}, ensure_ascii=False)
                con.execute(
                    "INSERT OR IGNORE INTO sources "
                    "(channel_id,name,url,kind,enabled,initialized,priority,legacy_config_json) "
                    "VALUES (?,?,?,'rss',1,0,?,?)",
                    (cid, name, url, priority, info),
                )
                if con.execute("SELECT changes()").fetchone()[0]:
                    added.append(name)
            report = {
                "channel_id": cid, "status": "applied",
                "disabled_dead_sources": retired, "new_feeds": added,
                "active_sources": int(con.execute(
                    "SELECT count(*) FROM sources WHERE channel_id=? AND enabled=1", (cid,),
                ).fetchone()[0]),
            }
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?)",
                (key, json.dumps({"timestamp": now_iso(), **report}, ensure_ascii=False)),
            )
            reports.append(report)
        con.commit()
    for row in reports:
        event("ingest", "2.3.23 commercial source repair applied", **row)
    return {"version": "2.3.23", "channels": reports}
