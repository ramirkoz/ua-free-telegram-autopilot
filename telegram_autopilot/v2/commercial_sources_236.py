"""2.3.6: complete the 2.3.5 commercial source roster without shared-feed collisions.

The installed operator 2.3.5 carried these source changes locally. GitHub
main v2.2.64 did not. This narrowly scoped migration makes the next official
portable compatible with imported 2.3.5 Data and with a fresh 2.2.64 Data
import. It fixes the FeedBurner HOST collision: Design Milk and Trend Hunter
are different publishers despite sharing feeds.feedburner.com.

No collector calls, no history replay, no channel-ID special cases.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .loghub import event
from .storage import now_iso

MARKER = "commercial_sources_236_once_channel_"

SHIPPED_ANCHORS = {
    ("Yanko Design", "https://www.yankodesign.com/feed/"),
    ("Creative Bloq", "https://www.creativebloq.com/feeds.xml"),
    ("Creative Boom", "https://www.creativeboom.com/feed/"),
    ("Campaign Brief", "https://campaignbrief.com/feed/"),
    ("Design Milk", "https://feeds.feedburner.com/design-milk"),
    ("Muse by Clio", "https://musebyclios.com/feed/"),
    ("It’s Nice That", "http://feeds2.feedburner.com/itsnicethat/SlXC"),
    ("Ads of the World", "https://www.adsoftheworld.com/"),
}
NEW_SOURCES = (
    ("designboom — Design", "https://www.designboom.com/design/feed/", 20),
    ("Dezeen — Design", "https://www.dezeen.com/design/feed/", 21),
    ("Packaging of the World", "https://packagingoftheworld.com/feed", 23),
    ("Colossal", "https://www.thisiscolossal.com/feed/", 30),
)
RESTORE = (
    ("The Dieline", "https://thedieline.com/", "https://thedieline.com/feed/", 11),
    ("Trend Hunter", "https://www.trendhunter.com/", "http://feeds.feedburner.com/TrendHunter/Top10", 55),
)


def _host(value: str) -> str:
    return (urlsplit(value).hostname or "").lower().removeprefix("www.")


def _publisher_taken(existing: list[Any], name: str, url: str) -> bool:
    """Compare publisher identity, never third-party delivery hosts alone."""
    for row in existing:
        if str(row["name"] or "").casefold() == name.casefold():
            return True  # Even disabled operator alternative is intentional.
        other_url = str(row["url"] or "")
        if other_url == url:
            return True
        # Source-owned URLs can share a publisher host; third-party RSS
        # relays (FeedBurner etc) are NOT evidence of shared publisher identity.
        relay_hosts = {"feeds.feedburner.com", "feeds2.feedburner.com"}
        host = _host(url)
        if host and host not in relay_hosts and host == _host(other_url):
            return True
    return False


def apply_commercial_sources_236(store: Any) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        channels = con.execute(
            "SELECT id FROM channels WHERE channel_mode='editorial' "
            "AND editorial_runtime_profile='commercial_editorial'"
        ).fetchall()
        for ch in channels:
            cid = int(ch["id"])
            key = MARKER + str(cid)
            if con.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone():
                changed.append({"channel_id": cid, "status": "already_applied"})
                continue
            rows = con.execute(
                "SELECT id,name,url,kind,enabled,initialized,priority,legacy_config_json "
                "FROM sources WHERE channel_id=?", (cid,),
            ).fetchall()
            if sum((str(row["name"] or ""), str(row["url"] or "")) in SHIPPED_ANCHORS for row in rows) < 3:
                changed.append({"channel_id": cid, "status": "custom_roster_preserved"})
                continue
            restored: list[str] = []
            added: list[str] = []
            for name, old_url, new_url, priority in RESTORE:
                matches = [
                    row for row in rows
                    if str(row["name"] or "") == name
                    and str(row["url"] or "") in (old_url, new_url)
                ]
                if len(matches) != 1:
                    continue
                row = matches[0]
                sid = int(row["id"])
                # If already enabled on the expected URL, respect existing
                # LIVE health/cooldowns (e.g. The Dieline HTTP_403).
                if str(row["url"] or "") == new_url and int(row["enabled"]):
                    continue
                if int(row["enabled"]) and str(row["url"] or "") != old_url:
                    continue
                conflict = con.execute(
                    "SELECT id FROM sources WHERE channel_id=? AND url=? AND id<>?",
                    (cid, new_url, sid),
                ).fetchone()
                if conflict:
                    continue
                try:
                    settings = json.loads(str(row["legacy_config_json"] or "{}"))
                except (ValueError, TypeError):
                    settings = {}
                if not isinstance(settings, dict):
                    settings = {}
                settings[MARKER] = {"previous_url": str(row["url"] or ""),
                    "source_owned_publisher": name,
                    "live_yield_verified": False, "source_history_preserved": True}
                con.execute(
                    "UPDATE sources SET url=?,kind='rss',enabled=1,initialized=0,"
                    "priority=?,last_checked_at='',last_error='',"
                    "legacy_config_json=? WHERE id=?",
                    (new_url, priority, json.dumps(settings, ensure_ascii=False), sid),
                )
                # Only clear stale cooldown when the URL/state actually
                # changed. Preserve cumulative success/failure counters.
                con.execute(
                    "UPDATE source_health SET consecutive_failures=0,cooldown_until='',"
                    "last_outcome='FEED_MIGRATED_236',last_error='',"
                    "zero_result_streak=0,slow_streak=0,last_duration_ms=0,"
                    "last_items=0,last_added=0,updated_at=? WHERE source_id=?",
                    (now_iso(), sid),
                )
                restored.append(name)
            # Requery after restoring before checking additions. Do not
            # overwrite or enable any operator alternative source entry.
            rows = con.execute(
                "SELECT id,name,url,kind,enabled,initialized,priority,legacy_config_json "
                "FROM sources WHERE channel_id=?", (cid,),
            ).fetchall()
            for name, url, priority in NEW_SOURCES:
                if _publisher_taken(rows, name, url):
                    continue
                note = json.dumps({MARKER: {"introduced": "2.3.6",
                    "source": name, "live_yield_verified": False,
                    "no_historical_replay": True}}, ensure_ascii=False)
                con.execute(
                    "INSERT OR IGNORE INTO sources "
                    "(channel_id,kind,name,url,enabled,initialized,priority,legacy_config_json)"
                    " VALUES (?,'rss',?,?,1,0,?,?)",
                    (cid, name, url, priority, note),
                )
                if int(con.execute("SELECT changes()").fetchone()[0]):
                    added.append(name)
                    rows = con.execute(
                        "SELECT id,name,url,kind,enabled,initialized,priority,legacy_config_json "
                        "FROM sources WHERE channel_id=?", (cid,),
                    ).fetchall()
            report = {"channel_id": cid, "status": "applied",
                      "restored": restored, "added": added}
            con.execute("INSERT INTO meta(key,value) VALUES(?,?)",
                        (key,json.dumps({"at": now_iso(), **report},ensure_ascii=False)))
            changed.append(report)
        con.commit()
    result = {"version": "2.3.6", "channels": changed}
    event("ingest", "2.3.6 exact publisher source migration", **result)
    return result
