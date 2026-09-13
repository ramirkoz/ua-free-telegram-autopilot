from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

from .. import collector
from ..database import content_hash
from ..models import CollectedArticle, Source
from . import ingest as base
from .loghub import event


class StrictTelegramParser(base.TelegramParser):
    """RC22 Telegram parser: exact message ownership + aggressive chrome rejection.

    The positive wrapper allowlist used in RC19-RC21 was too brittle: Telegram can
    change or omit wrapper class names while the media still belongs to the exact
    ``data-post`` widget. The parser already creates ``current`` only inside that
    widget, so the widget itself is the positive ownership boundary. RC22 accepts
    media anywhere inside that exact widget unless the element/ancestor classes
    identify known Telegram chrome, previews, avatars, reactions or promotional UI.
    """

    _NON_CONTENT_MEDIA_MARKERS = base.TelegramParser._NON_CONTENT_MEDIA_MARKERS | {
        "tgme_widget_message_owner_photo",
        "tgme_widget_message_from_photo",
        "tgme_widget_message_forwarded_from",
        "tgme_widget_message_reply",
        "tgme_widget_message_reply_thumb",
        "tgme_widget_message_link_preview",
        "tgme_widget_message_webpage",
        "tgme_channel_info",
        "tgme_channel_photo",
        "peer_photo",
        "channel_photo",
        "channel_avatar",
        "sender_photo",
        "message_author_photo",
        "link_preview",
        "webpage_preview",
        "reply_preview",
        "forward_header",
        "brandmark",
        "brand_logo",
        "channel_logo",
        "site_logo",
        "promo",
        "sponsor",
        "subscribe",
        "follow_button",
    }

    def _add_media(self, kind: str, url: str, classes: set[str]) -> None:
        if self.current is None:
            return
        # ``self.current`` is opened only by one concrete Telegram data-post.
        # Do not require Telegram's unstable content-wrapper class names here.
        # The base implementation still applies the expanded ancestor blacklist,
        # video-poster rejection and duplicate identity filter.
        super()._add_media(kind, url, classes)


def _article_v4(username: str, entry: base.TelegramEntry) -> CollectedArticle:
    article = base._to_article(username, entry, [])
    try:
        layout = json.loads(str(article.article_layout_json or "{}"))
    except Exception:
        layout = {}
    if not isinstance(layout, dict):
        layout = {}
    tg = layout.get("telegram")
    if not isinstance(tg, dict):
        tg = {}
        layout["telegram"] = tg
    tg["media_filter_version"] = 4
    tg["stitched"] = False
    article.article_layout_json = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
    return article


def strict_stitch_telegram(username: str, entries: list[base.TelegramEntry]) -> list[CollectedArticle]:
    """One Telegram data-post widget is one article; neighbours never donate media."""
    ordered = sorted(
        entries,
        key=lambda entry: (
            base._post_number(entry.post) is None,
            base._post_number(entry.post) if base._post_number(entry.post) is not None else 10**18,
        ),
    )
    return [_article_v4(username, entry) for entry in ordered if entry.text]


def collect_telegram_strict(source: Source) -> list[CollectedArticle]:
    username = collector._telegram_username(source.url)
    if not username:
        raise collector.CollectorError("Telegram-джерело має містити публічну адресу t.me/username")
    response = collector._source_fetch(
        f"https://t.me/s/{username}",
        max_bytes=8 * 1024 * 1024,
        allowed_content_types={"text/html", "application/xhtml+xml"},
        timeout=35,
    )
    parser = StrictTelegramParser(username)
    parser.feed(response.body.decode("utf-8", errors="replace"))
    parser.close()
    items = strict_stitch_telegram(username, parser.entries)
    if not items:
        raise collector.CollectorError("Не вдалося прочитати Telegram-канал")
    return items[-40:]


def collect_strict(source: Source) -> list[CollectedArticle]:
    return collect_telegram_strict(source) if source.kind == "telegram" else collector.collect_source(source)


class StrictIngestService(base.IngestService):
    """Strict Telegram ownership with the existing parallel/source-health scheduler."""

    def collect_channel(self, channel_id: int, heartbeat: Callable[[], None] | None = None) -> dict[str, int]:
        added = seen = errors = skipped = 0

        def beat() -> None:
            if heartbeat is not None:
                try:
                    heartbeat()
                except Exception:
                    pass

        sources: list[Source] = []
        for row in self.store.sources_for_channel(channel_id, enabled_only=True):
            beat()
            source = Source(
                id=int(row["id"]), channel_id=int(row["channel_id"]), kind=str(row["kind"]),
                name=str(row["name"]), url=str(row["url"]), enabled=bool(row["enabled"]),
                initialized=bool(row["initialized"]), last_checked_at=str(row["last_checked_at"] or "") or None,
                last_error=str(row["last_error"] or "") or None, priority=int(row["priority"] or 100),
            )
            cooling, cooldown_until = self.store.source_cooldown_active(source.id)
            if cooling:
                skipped += 1
                event(
                    "ingest", "source cooldown skip", channel_id=channel_id, source_id=source.id,
                    source=source.name, cooldown_until=cooldown_until,
                )
                continue
            sources.append(source)

        def fetch_one(source: Source) -> tuple[list[CollectedArticle], int]:
            started = time.monotonic()
            with base._GLOBAL_SOURCE_FETCH_LIMIT:
                items = collect_strict(source)
            return items, int(max(0.0, time.monotonic() - started) * 1000)

        max_workers = max(1, min(3, len(sources)))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"ingest-{channel_id}") as pool:
            future_map = {pool.submit(fetch_one, source): (source, time.monotonic()) for source in sources}
            for future in as_completed(future_map):
                source, submitted_at = future_map[future]
                beat()
                try:
                    items, duration_ms = future.result()
                    seen += len(items)
                    source_added = 0
                    for item in items:
                        media_json = json.dumps(list(item.media_urls or []), ensure_ascii=False, separators=(",", ":"))
                        before = self._existing(channel_id, source.id, item.external_id, item.url)
                        self.store.insert_collected(
                            channel_id=channel_id, source_id=source.id, external_id=item.external_id,
                            title=item.title, source_url=item.url, raw_text=item.raw_text,
                            content_hash=content_hash(item.title, item.raw_text),
                            source_published_at=str(item.published_at or ""), media_json=media_json,
                            article_layout_json=str(item.article_layout_json or "{}"),
                        )
                        if not before:
                            added += 1
                            source_added += 1
                        beat()
                    self.store.record_source_success(source.id, duration_ms)
                    with self.store.connect() as con:
                        con.execute(
                            "UPDATE sources SET initialized=1,last_checked_at=?,last_error='' WHERE id=?",
                            (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), source.id),
                        )
                    event(
                        "ingest", "source collected", channel_id=channel_id, source_id=source.id,
                        source=source.name, items=len(items), added=source_added, duration_ms=duration_ms,
                    )
                except Exception as exc:
                    errors += 1
                    duration_ms = int(max(0.0, time.monotonic() - submitted_at) * 1000)
                    failures, cooldown = self.store.record_source_failure(source.id, duration_ms, str(exc))
                    with self.store.connect() as con:
                        con.execute(
                            "UPDATE sources SET last_checked_at=?,last_error=? WHERE id=?",
                            (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), str(exc)[:1200], source.id),
                        )
                    event(
                        "ingest", "source collection failed", level=40, channel_id=channel_id,
                        source_id=source.id, source=source.name, detail=str(exc)[:600], duration_ms=duration_ms,
                        consecutive_failures=failures, cooldown_until=cooldown,
                    )
                finally:
                    beat()
        return {"seen": seen, "added": added, "errors": errors, "skipped_cooldown": skipped}
