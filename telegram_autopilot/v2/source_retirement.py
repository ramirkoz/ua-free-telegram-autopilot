"""One-time retirement of sources that refuse automated reading.

Operator decision 2026-10-19 (2.2.3): sources whose sites block automated
requests (HTTP 403 on pages or on all article images) are removed from
collection. They are DISABLED, not deleted: deleting a source cascades to its
article history, and a disabled source can be re-enabled in channel settings.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .loghub import event
from .storage import now_iso

MIGRATION_KEY = "autopilot_223_blocked_sources_retired"

# Registrable domains of the retired sources (any subdomain matches).
RETIRED_SOURCE_DOMAINS = (
    "trendhunter.com",      # pages load, every CDN image answers 403 (Akamai)
    "lbbonline.com",        # Little Black Book: 403 on every request
    "thedieline.com",       # The Dieline: 403
    "campaignlive.co.uk",   # Campaign: 403
    "campaignlive.com",
    "designtaxi.com",       # DesignTAXI: 403
)


# Fallback by operator-visible name, used only together with live evidence of a
# block (last outcome HTTP 403) because exact feed URLs differ per install.
RETIRED_SOURCE_NAMES = ("trend hunter", "trendhunter", "little black book", "the dieline", "campaign", "designtaxi")


def _host(url: str) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").casefold()
    except ValueError:
        return ""


def is_retired_source_url(url: str) -> bool:
    host = _host(url)
    return any(host == domain or host.endswith("." + domain) for domain in RETIRED_SOURCE_DOMAINS)


def retire_blocked_sources_once(store: Any) -> dict[str, Any]:
    stamp = now_iso()
    retired: list[str] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM meta WHERE key=?", (MIGRATION_KEY,)).fetchone():
            con.commit()
            return {"skipped": 1, "retired": []}
        rows = con.execute(
            """SELECT s.id,s.channel_id,s.name,s.url,COALESCE(h.last_outcome,'') AS last_outcome
                 FROM sources s LEFT JOIN source_health h ON h.source_id=s.id WHERE s.enabled=1"""
        ).fetchall()
        for row in rows:
            name = " ".join(str(row["name"] or "").casefold().split())
            by_name = name in RETIRED_SOURCE_NAMES and (
                str(row["last_outcome"]) == "HTTP_403" or name in {"trend hunter", "trendhunter"}
            )
            if not (is_retired_source_url(str(row["url"] or "")) or by_name):
                continue
            con.execute(
                "UPDATE sources SET enabled=0,last_error=? WHERE id=?",
                ("Вимкнено в 2.2.3: сайт блокує автоматичне читання (HTTP 403). Можна ввімкнути вручну.", int(row["id"])),
            )
            retired.append(f"{row['name']} (channel {int(row['channel_id'])})")
        con.execute("INSERT INTO meta(key,value) VALUES(?,?)", (MIGRATION_KEY, stamp))
        con.commit()
    event("ingest", "2.2.3 retired sources blocking automated reading", retired=retired, count=len(retired))
    return {"skipped": 0, "retired": retired}
