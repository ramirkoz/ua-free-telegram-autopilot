from __future__ import annotations

"""Telegram source composition policy for the current V2 runtime.

The strict parser still owns media by exact ``data-post``. This module composes one
bounded editorial item when a text-only message and an immediately adjacent
media-only message are consecutive and fall inside the existing five-minute window.
No media is borrowed across a text-bearing neighbour or a non-consecutive message.
"""

from .. import collector
from ..models import CollectedArticle, Source
from . import bounded_ingest
from . import ingest as base
from . import strict_ingest


def stitch_adjacent_telegram_media(username: str, entries: list[base.TelegramEntry]) -> list[CollectedArticle]:
    """Use exact Telegram media ownership, never just consecutive post IDs.

    Older adjacent 4655-video + 4656-text/photo would create a false album.
    The strict stitcher only allows explicit grouped/reply/source-video links.
    """
    return strict_ingest.strict_stitch_telegram(username, entries)


def collect_telegram_current(source: Source) -> list[CollectedArticle]:
    username = collector._telegram_username(source.url)
    if not username:
        raise collector.CollectorError("Telegram-джерело має містити публічну адресу t.me/username")
    response = collector._source_fetch(
        f"https://t.me/s/{username}",
        max_bytes=8 * 1024 * 1024,
        allowed_content_types={"text/html", "application/xhtml+xml"},
        timeout=35,
    )
    parser = strict_ingest.StrictTelegramParser(username)
    parser.feed(response.body.decode("utf-8", errors="replace"))
    parser.close()
    entries = [strict_ingest._hydrate_exact_video_post(username, entry) for entry in parser.entries]
    items = stitch_adjacent_telegram_media(username, entries)
    if not items:
        raise collector.CollectorError("Не вдалося прочитати Telegram-канал")
    return items[-40:]


def _collect_current(
    source: Source,
    *,
    page_prefer_feed: bool = False,
    page_candidate_scan_limit: int = 24,
    page_fetch_limit: int = 8,
) -> list[CollectedArticle]:
    if source.kind == "telegram":
        return collect_telegram_current(source)
    return collector.collect_source(
        source,
        page_prefer_feed=page_prefer_feed,
        page_candidate_scan_limit=page_candidate_scan_limit,
        page_fetch_limit=page_fetch_limit,
    )


def install_ingest_behavior() -> None:
    """Install only the collector hook used by the bounded production scheduler."""
    if getattr(bounded_ingest, "_adjacent_ingest_policy_installed", False):
        return
    bounded_ingest.collect_strict = _collect_current
    bounded_ingest._adjacent_ingest_policy_installed = True
