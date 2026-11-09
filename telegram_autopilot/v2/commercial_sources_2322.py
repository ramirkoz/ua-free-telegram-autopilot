"""v2.3.22: shift ПРОДАНО! from trade press to consumer-shareable stories.

This migration is idempotent, scoped to the canonical commercial preset and
exact name+URL pairs. Disabled historical sources are kept for foreign keys;
any custom/user-edited row, unknown channel and source history stay intact.
Feed-directory checks do NOT prove operator-network HTTP/media acceptance.
No old articles get requeued and no publisher media restrictions are weakened.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .loghub import event
from .storage import now_iso

PREFIX = "commercial_sources_2322_once_channel_"
ANCHORS = {
    ("Yanko Design", "https://www.yankodesign.com/feed/"),
    ("Creative Bloq", "https://www.creativebloq.com/feeds.xml"),
    ("Muse by Clio", "https://musebyclios.com/feed/"),
    ("Campaign Brief", "https://campaignbrief.com/feed/"),
}
# Exact operator source pairs, not fuzzy domain exclusions.
# These are trade-marketing, agency/staffing and/or nonfunctional 403 sources.
RETIRE_EXACT: dict[str, str] = {
    "Famous Campaigns": "https://www.famouscampaigns.com/2026/",
    "Campaigns of the World": "https://campaignsoftheworld.com/",
    "Muse by Clio": "https://musebyclios.com/feed/",
    "Campaign Brief": "https://campaignbrief.com/feed/",
    "Shots": "https://shots.net/the-work",
    "Creative Review": "https://www.creativereview.co.uk/feed/",
    "The PR Insider": "https://www.theprinsider.com/pr-campaign-list",
    "Adweek": "https://www.adweek.com/feed/",
    "Ads of the World": "https://www.adsoftheworld.com/",
    "The Drum": "https://www.thedrum.com/",
    "Contagious": "https://www.contagious.com/en",
    "Ad Age": "https://adage.com/news/",
    "The Dieline": "https://thedieline.com/feed/",
    "COOL HUNTING": "https://coolhunting.com/feed/",
}
# Keep these broad-audience/art/creative sources, preserve their existing URLs.
PRIORITIZE_EXACT: dict[str, tuple[str, int]] = {
    "It’s Nice That": ("http://feeds2.feedburner.com/itsnicethat/SlXC", 10),
    "Yanko Design": ("https://www.yankodesign.com/feed/", 12),
    "Creative Boom": ("https://www.creativeboom.com/feed/", 14),
    "Creative Bloq": ("https://www.creativebloq.com/feeds.xml", 18),
    "designboom — Design": ("https://www.designboom.com/design/feed/", 18),
    "Colossal": ("https://www.thisiscolossal.com/feed/", 16),
    "Dezeen — Design": ("https://www.dezeen.com/design/feed/", 20),
    "Design Milk": ("https://feeds.feedburner.com/design-milk", 22),
    "Design You Trust": ("https://designyoutrust.com/feed/", 23),
    "Packaging of the World": ("https://packagingoftheworld.com/feed", 25),
    "Core77": ("http://www.core77.com/feed/", 28),
    "Trend Hunter": ("http://feeds.feedburner.com/TrendHunter/Top10", 28),
    "Fast Company": ("https://www.fastcompany.com/co-design/rss", 32),
}
# Externally verified active recent public feeds, publisher-network LIVE pending.
FRESH: tuple[tuple[str, str, int], ...] = (
    ("My Modern Met", "https://mymodernmet.com/feed/", 13),
    ("Laughing Squid", "https://laughingsquid.com/feed/", 15),
)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def apply_commercial_sources_2322(store: Any) -> dict[str, Any]:
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
                "SELECT id,name,url,kind,enabled,priority FROM sources "
                "WHERE channel_id=?", (cid,)
            ).fetchall()
            if sum((str(r["name"]), str(r["url"])) in ANCHORS for r in rows) < 3:
                reports.append({"channel_id": cid, "status": "custom_preserved"})
                continue
            retired, promoted, added = [], [], []
            for r in rows:
                name, url = str(r["name"]), str(r["url"])
                if RETIRE_EXACT.get(name) == url and int(r["enabled"]):
                    con.execute("UPDATE sources SET enabled=0 WHERE id=?", (int(r["id"]),))
                    retired.append(name)
                pair = PRIORITIZE_EXACT.get(name)
                if pair and pair[0] == url and int(r["priority"]) != pair[1]:
                    con.execute(
                        "UPDATE sources SET priority=? WHERE id=?",
                        (pair[1], int(r["id"])),
                    )
                    promoted.append(name)
            hosts = {_host(str(r["url"])) for r in rows}
            names = {str(r["name"]).casefold() for r in rows}
            for name, url, priority in FRESH:
                if not _host(url) or _host(url) in hosts or name.casefold() in names:
                    continue
                info = json.dumps({"commercial_sources_2322": {
                    "introduced_in": "2.3.22",
                    "public_feed_current": True,
                    "operator_network_and_media_validated": False,
                    "source_audience": "broad_culture_creative_and_curiosity",
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
                    names.add(name.casefold())
                    hosts.add(_host(url))
            report = {
                "channel_id": cid, "status": "applied",
                "disabled_trade_sources": retired,
                "reprioritized_consumer_sources": promoted,
                "new_consumer_feeds": added,
                "active_sources": int(con.execute(
                    "SELECT count(*) FROM sources WHERE channel_id=? AND enabled=1",
                    (cid,),
                ).fetchone()[0]),
            }
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?)",
                (key, json.dumps({"timestamp": now_iso(), **report}, ensure_ascii=False)),
            )
            reports.append(report)
        con.commit()
    for row in reports:
        event("ingest", "2.3.22 consumer source portfolio applied", **row)
    return {"version": "2.3.22", "channels": reports, "live_feed_yield_unverified": True}
