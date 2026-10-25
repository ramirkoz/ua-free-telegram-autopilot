"""2.2.29: one-time, narrowly scoped commercial discovery-source refresh.

Operator decision: refresh the existing broad-audience commercial source mix,
not the editorial threshold, interval, AI provider list, or media policy.
Disabled sources are NEVER deleted because article history has foreign keys to
source IDs. Previously unknown/custom source entries are not modified.

New endpoints have public-site/feed evidence; their real collector yield must
still be verified on the operator machine. This module does no startup network
requests and never silently retries 403-blocked old sources.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from typing import Any

from .domain import EditorialRuntimeProfile
from .loghub import event
from .storage import now_iso

PACK_VERSION = "2.2.29"
META_PREFIX = "commercial_sources_229_once_channel_"

# A few narrowly targeted high-yield consumer/creative discovery sources.
# Public endpoint visibility is NOT proof of operator-network collector success.
SOURCE_ADDITIONS: tuple[tuple[str, str, str, int], ...] = (
    ("Campaigns of the World", "https://campaignsoftheworld.com/", "page", 12),
    ("Yanko Design", "https://www.yankodesign.com/feed/", "rss", 18),
    ("Creative Bloq", "https://www.creativebloq.com/feeds.xml", "rss", 22),
    ("Design Milk", "https://design-milk.com/feed/", "rss", 25),
    ("The PR Insider", "https://www.theprinsider.com/pr-campaign-list", "page", 32),
)

# Match BOTH name and exact canonical operator URL. Never silence user-added
# sources or broad domains based on a name substring.
RETIRE_LOW_YIELD: dict[str, str] = {
    "Springwise": "https://springwise.com/",
    "Snapchat for Business": "https://forbusiness.snapchat.com/blog",
    "YouTube Blog": "https://blog.youtube/",
    "Meta News": "https://about.fb.com/feed/",
    "LinkedIn Marketing Blog": "https://www.linkedin.com/business/marketing/blog",
    "Social Media Today": "https://www.socialmediatoday.com/feeds/news/",
    "Marketing Dive": "https://www.marketingdive.com/feeds/news/",
    "Digiday": "https://digiday.com/feed/",
    "Reddit for Business": "https://www.business.reddit.com/blog",
    "Pinterest Business Blog": "https://business.pinterest.com/blog/",
    "Think with Google": "https://business.google.com/en-all/think/",
    "Brand New / UnderConsideration": "https://www.underconsideration.com/brandnew/feed/thefollowup/the_follow_up/",
    "Social Samosa": "https://www.socialsamosa.com/rss",
}

# Only previously known official-source rows get source priority updates.
PROMOTE_EXISTING: dict[str, tuple[str, int]] = {
    "Muse by Clio": ("https://musebyclios.com/feed/", 14),
    "It’s Nice That": ("http://feeds2.feedburner.com/itsnicethat/SlXC", 16),
    "Creative Boom": ("https://www.creativeboom.com/feed/", 20),
    "Adweek": ("https://www.adweek.com/", 35),
    "Fast Company": ("https://www.fastcompany.com/", 42),
    "Creative Review": ("https://www.creativereview.co.uk/feed/", 24),
    "Ads of the World": ("https://www.adsoftheworld.com/", 28),
}
FAMOUS_RSS = "https://www.famouscampaigns.com/feed/"
FAMOUS_PAGE = "https://www.famouscampaigns.com/"


def _host(value: str) -> str:
    try:
        return (urlsplit(value).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _operator_known(row: Any, known: dict[str, str]) -> bool:
    return str(row["name"] or "") in known and str(row["url"] or "") == known[str(row["name"])]


def apply_commercial_sources_229(store: Any) -> dict[str, Any]:
    """Apply once per existing commercial_editorial channel, never by channel ID.

    This is an explicit release migration, not a generic auto-learning rule.
    It touches only exact known source identities. Custom sources and all
    other channels remain unchanged. A simple transaction rolls back failures.
    """
    results: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        channels = con.execute(
            "SELECT id,name FROM channels WHERE editorial_runtime_profile=?",
            (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
        ).fetchall()
        for channel in channels:
            channel_id = int(channel["id"])
            key = META_PREFIX + str(channel_id)
            if con.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone():
                results.append({"channel_id": channel_id, "outcome": "already_applied"})
                continue
            rows = con.execute(
                "SELECT id,name,url,kind,priority,enabled,legacy_config_json FROM sources WHERE channel_id=?",
                (channel_id,),
            ).fetchall()
            if not rows:
                # Fresh channel/import in progress: do NOT mark migration done.
                results.append({"channel_id": channel_id, "outcome": "no_sources_yet"})
                continue
            known_urls = dict(RETIRE_LOW_YIELD)
            known_urls.update({name: pair[0] for name, pair in PROMOTE_EXISTING.items()})
            known_urls["Famous Campaigns"] = FAMOUS_RSS
            if sum(_operator_known(row, known_urls) for row in rows) < 4:
                # A custom commercial channel is not the shipped operator feed.
                results.append({"channel_id": channel_id, "outcome": "custom_sources_unchanged"})
                continue
            retired: list[str] = []
            promoted: list[str] = []
            added: list[str] = []
            for row in rows:
                name = str(row["name"] or "")
                current_url = str(row["url"] or "")
                if name in RETIRE_LOW_YIELD and current_url == RETIRE_LOW_YIELD[name] and int(row["enabled"]):
                    con.execute("UPDATE sources SET enabled=0 WHERE id=?", (int(row["id"]),))
                    retired.append(name)
                pair = PROMOTE_EXISTING.get(name)
                if pair and current_url == pair[0] and int(row["priority"]) != pair[1]:
                    con.execute("UPDATE sources SET priority=? WHERE id=?", (pair[1], int(row["id"])))
                    promoted.append(name)
                if name == "Famous Campaigns" and current_url == FAMOUS_RSS:
                    conflict = con.execute(
                        "SELECT id FROM sources WHERE channel_id=? AND url=? AND id<>?",
                        (channel_id, FAMOUS_PAGE, int(row["id"])),
                    ).fetchone()
                    if conflict is None:
                        try:
                            extras = json.loads(str(row["legacy_config_json"] or "{}"))
                        except (ValueError, TypeError):
                            extras = {}
                        if not isinstance(extras, dict):
                            extras = {}
                        extras["commercial_sources_229"] = {
                            "previous_kind": str(row["kind"]), "previous_url": current_url,
                            "reason": "RSS showed no new articles while public homepage had new campaigns",
                        }
                        con.execute(
                            "UPDATE sources SET kind='page',url=?,priority=10,initialized=0,"
                            "last_checked_at='',last_error='',legacy_config_json=? WHERE id=?",
                            (FAMOUS_PAGE, json.dumps(extras, ensure_ascii=False), int(row["id"])),
                        )
                        promoted.append("Famous Campaigns (homepage recovery)")
            # Do not silently revive a previously disabled domain or create
            # duplicates of a user-entered alternative URL on the same site.
            existing_hosts = {_host(str(row["url"] or "")) for row in rows}
            for name, url, kind, priority in SOURCE_ADDITIONS:
                if _host(url) in existing_hosts:
                    continue
                source_payload = json.dumps({
                    "commercial_sources_229": {
                        "introduced_in": PACK_VERSION,
                        "operator_collector_verified": False,
                        "note": "public feed/site exists; inspect first live ingestion and media",
                    }
                }, ensure_ascii=False)
                con.execute(
                    "INSERT OR IGNORE INTO sources"
                    "(channel_id,kind,name,url,enabled,initialized,priority,legacy_config_json)"
                    " VALUES(?,?,?,?,1,0,?,?)",
                    (channel_id, kind, name, url, priority, source_payload),
                )
                if con.execute(
                    "SELECT changes()"
                ).fetchone()[0]:
                    added.append(name)
                    existing_hosts.add(_host(url))
            report = {
                "channel_id": channel_id, "outcome": "applied",
                "retired": retired, "promoted": promoted, "added": added,
                "active_sources": int(con.execute(
                    "SELECT count(*) FROM sources WHERE channel_id=? AND enabled=1",
                    (channel_id,),
                ).fetchone()[0]),
            }
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?)",
                (key, json.dumps({"at": now_iso(), **report}, ensure_ascii=False)),
            )
            results.append(report)
        con.commit()
    for result in results:
        event("ingest", "2.2.29 commercial source refresh", **result)
    return {"version": PACK_VERSION, "channels": results}


__all__ = ["apply_commercial_sources_229", "SOURCE_ADDITIONS", "RETIRE_LOW_YIELD"]
