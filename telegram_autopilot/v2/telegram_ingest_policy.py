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
    ordered = sorted(
        entries,
        key=lambda entry: (
            base._post_number(entry.post) is None,
            base._post_number(entry.post) if base._post_number(entry.post) is not None else 10**18,
        ),
    )
    entry_by_id = {
        int(post_id): entry
        for entry in ordered
        if (post_id := base._post_number(entry.post)) is not None
    }

    def media_only(entry: base.TelegramEntry) -> bool:
        return not str(entry.text or "").strip() and strict_ingest._strict_media_bearing(entry)

    articles: list[CollectedArticle] = []
    i = 0
    while i < len(ordered):
        current = ordered[i]

        if media_only(current):
            run = [current]
            j = i + 1
            while j < len(ordered) and media_only(ordered[j]) and base._adjacent(run[-1], ordered[j]):
                run.append(ordered[j])
                j += 1
            if j < len(ordered):
                primary = ordered[j]
                if str(primary.text or "").strip() and not primary.media and base._adjacent(run[-1], primary):
                    attached = list(run)
                    k = j + 1
                    previous = primary
                    while k < len(ordered) and media_only(ordered[k]) and base._adjacent(previous, ordered[k]):
                        attached.append(ordered[k])
                        previous = ordered[k]
                        k += 1
                    article = base._to_article(username, primary, attached)
                    articles.append(strict_ingest._upgrade_strict_article(username, article, entry_by_id))
                    i = k
                    continue
            i = j
            continue

        if str(current.text or "").strip():
            attached: list[base.TelegramEntry] = []
            j = i + 1
            previous = current
            while j < len(ordered) and media_only(ordered[j]) and base._adjacent(previous, ordered[j]):
                attached.append(ordered[j])
                previous = ordered[j]
                j += 1

            if not current.media and not attached and j >= len(ordered) and base._held(current):
                i = j
                continue

            article = base._to_article(username, current, attached)
            articles.append(strict_ingest._upgrade_strict_article(username, article, entry_by_id))
            i = j
            continue

        i += 1

    return articles


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
