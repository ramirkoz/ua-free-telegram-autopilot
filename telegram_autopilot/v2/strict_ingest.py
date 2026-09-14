from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

from .. import collector
from ..database import content_hash
from ..media import encode_media, media_identity
from ..models import CollectedArticle, Source
from . import ingest as base
from .loghub import event


class StrictTelegramParser(base.TelegramParser):
    """Exact Telegram message ownership without throwing away real post media.

    Telegram has changed its public ``t.me/s`` wrappers several times.  RC27 treated
    ``link_preview``/``webpage`` ancestors as an unconditional rejection.  In the
    current public HTML those wrapper classes can also surround a genuine
    ``tgme_widget_message_photo_wrap`` / grouped-media item.  That made every image
    candidate look like chrome and starved required-media monitoring channels.

    One concrete ``data-post`` widget is still the ownership boundary.  Hard chrome
    (avatar/reaction/reply/logo/promo) stays rejected.  Soft preview wrappers are
    ignored only when the candidate is positively inside Telegram's direct
    photo/video/grouped-media wrappers.
    """

    _DIRECT_CONTENT_MEDIA_MARKERS = {
        "tgme_widget_message_photo_wrap",
        "tgme_widget_message_photo",
        "tgme_widget_message_video_player",
        "tgme_widget_message_video",
        "tgme_widget_message_grouped_wrap",
        "tgme_widget_message_grouped_layer",
        "grouped_media_wrap",
        "grouped_media_layer",
        "js-message_photo",
        "js-message_video",
    }
    _SOFT_PREVIEW_MARKERS = {
        "tgme_widget_message_link_preview",
        "tgme_widget_message_webpage",
        "link_preview_image",
        "link_preview",
        "webpage_preview",
    }
    # Telegram changes CSS class names far more often than anyone sensible would
    # choose for a public transport contract.  These semantic fragments let exact
    # same-message photo/video wrappers survive class drift without opening the
    # door to avatars/reactions/replies, which are still hard-rejected below.
    _GENERIC_DIRECT_MEDIA_HINTS = (
        "photo", "video", "media", "album", "grouped", "attachment", "gallery",
    )

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

    def _generic_direct_content(self, classes: set[str]) -> bool:
        folded = {str(item or "").casefold() for item in classes}
        return any(hint in cls for cls in folded for hint in self._GENERIC_DIRECT_MEDIA_HINTS)

    def _remember_preview_fallback(self, kind: str, url: str) -> None:
        """Keep one exact-post preview candidate as a last-resort image.

        Municipal Telegram channels often publish a link card instead of attaching a
        separate photo.  RC28 treated every link-preview image as chrome, which left
        required-media channels permanently empty.  The preview still belongs to the
        exact ``data-post`` widget, so using it *only when no direct media exists* is
        safer than borrowing media from a neighbouring Telegram message.
        """
        if self.current is None or str(kind).casefold() != "image":
            return
        value = str(url or "").strip()
        if not value:
            return
        key = media_identity("image", value)
        keys = self.current.setdefault("preview_media_keys", set())
        assert isinstance(keys, set)
        if key in keys:
            return
        keys.add(key)
        candidates = self.current.setdefault("preview_media_candidates", [])
        assert isinstance(candidates, list)
        candidates.append(encode_media("image", value)[:3020])

    def _add_media(self, kind: str, url: str, classes: set[str]) -> None:
        if self.current is None:
            return
        self.current["raw_media_candidates"] = int(self.current.get("raw_media_candidates") or 0) + 1

        if str(kind).casefold() == "image" and self._contains_marker(classes, self._VIDEO_THUMB_MARKERS):
            self.current["discarded_video_thumb"] = int(self.current.get("discarded_video_thumb") or 0) + 1
            return

        hard_markers = set(self._NON_CONTENT_MEDIA_MARKERS) - set(self._SOFT_PREVIEW_MARKERS)
        if self._contains_marker(classes, hard_markers):
            self.current["discarded_non_content"] = int(self.current.get("discarded_non_content") or 0) + 1
            return

        direct_content = self._contains_marker(classes, self._DIRECT_CONTENT_MEDIA_MARKERS) or self._generic_direct_content(classes)
        soft_preview = self._contains_marker(classes, self._SOFT_PREVIEW_MARKERS)
        if not direct_content and soft_preview:
            self._remember_preview_fallback(kind, url)
            self.current["discarded_non_content"] = int(self.current.get("discarded_non_content") or 0) + 1
            return

        value = str(url or "").strip()
        if not value:
            return
        key = media_identity(kind, value)
        keys = self.current.setdefault("media_keys", set())
        assert isinstance(keys, set)
        if key in keys:
            self.current["discarded_duplicate"] = int(self.current.get("discarded_duplicate") or 0) + 1
            return
        keys.add(key)
        media = self.current.setdefault("media", [])
        assert isinstance(media, list)
        media.append(encode_media(kind, value)[:3020])

    def _finish(self) -> None:
        # Direct source media always wins.  If the exact Telegram widget contains no
        # direct attachment, allow a single exact-post link-preview image.  Never
        # stitch from a neighbouring data-post, so the ownership boundary remains
        # deterministic.
        if self.current is not None:
            media = self.current.setdefault("media", [])
            previews = self.current.get("preview_media_candidates")
            if isinstance(media, list) and not media and isinstance(previews, list) and previews:
                media.append(str(previews[0]))
                self.current["preview_fallback_used"] = 1
        super()._finish()


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
    tg["media_filter_version"] = 5
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
