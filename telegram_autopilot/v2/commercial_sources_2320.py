"""2.3.20: cautiously add externally-verified broad creative RSS inputs.

Sources were observed responding in public feed directories 08 Nov 2026,
NOT tested on operator Windows network. Never bypass HTTP403 on The Dieline,
never delete old articles/sources or mutate any custom publisher row.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from typing import Any

from .loghub import event
from .storage import now_iso

PREFIX = "commercial_sources_2320_once_channel_"
SOURCES = (
    ("COOL HUNTING", "https://coolhunting.com/feed/", 26),
    ("Core77", "http://www.core77.com/feed/", 28),
    ("Design You Trust", "https://designyoutrust.com/feed/", 30),
)
ANCHORS = {
    ("Yanko Design", "https://www.yankodesign.com/feed/"),
    ("Creative Bloq", "https://www.creativebloq.com/feeds.xml"),
    ("Muse by Clio", "https://musebyclios.com/feed/"),
    ("Campaign Brief", "https://campaignbrief.com/feed/"),
}


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold()
    return host[4:] if host.startswith("www.") else host


def apply_commercial_sources_2320(store: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        channels = con.execute(
            "SELECT id FROM channels WHERE channel_mode='editorial' "
            "AND editorial_runtime_profile='commercial_editorial'"
        ).fetchall()
        for channel in channels:
            cid = int(channel["id"])
            marker = PREFIX + str(cid)
            if con.execute("SELECT 1 FROM meta WHERE key=?", (marker,)).fetchone():
                results.append({"channel_id": cid, "status": "already_applied"})
                continue
            original = con.execute(
                "SELECT id,name,url FROM sources WHERE channel_id=?", (cid,)
            ).fetchall()
            if sum((str(s["name"]), str(s["url"])) in ANCHORS for s in original) < 3:
                results.append({"channel_id": cid, "status": "custom_profile_unchanged"})
                continue
            hosts = {_host(str(s["url"])) for s in original}
            names = {str(s["name"]).casefold() for s in original}
            added, skipped = [], []
            for name, url, priority in SOURCES:
                host = _host(url)
                if not host or host in hosts or name.casefold() in names:
                    skipped.append(name)
                    continue
                detail = json.dumps({"commercial_sources_2320": {
                    "created_in": "2.3.20",
                    "feed_directory_verified": True,
                    "operator_network_verified": False,
                    "original_url": url,
                    "requires_source_media": True,
                }}, ensure_ascii=False)
                con.execute(
                    "INSERT OR IGNORE INTO sources "
                    "(channel_id,name,url,kind,enabled,initialized,priority,legacy_config_json) "
                    "VALUES (?,?,?,'rss',1,0,?,?)",
                    (cid, name, url, int(priority), detail)
                )
                if con.execute("SELECT changes()").fetchone()[0]:
                    row = con.execute(
                        "SELECT id FROM sources WHERE channel_id=? AND url=?",
                        (cid, url),
                    ).fetchone()
                    added.append({"name": name, "source_id": int(row["id"])})
                    hosts.add(host)
                    names.add(name.casefold())
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?)",
                (marker, json.dumps({
                    "date": now_iso(), "added": added, "skipped": skipped,
                }, ensure_ascii=False)),
            )
            results.append({"channel_id": cid, "status": "applied",
                            "added": added, "skipped": skipped})
        con.commit()
    for row in results:
        event("ingest", "2.3.20 commercial RSS candidates registered", **row)
    return {"channels": results, "operator_network_verified": False}
