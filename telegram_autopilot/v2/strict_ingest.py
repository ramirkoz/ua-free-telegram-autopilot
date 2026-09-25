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

    RC33 also preserves ``href`` targets that Telegram hides behind visible anchor
    text inside the message body.  Operational links such as registration/application
    forms must survive ingest so editorial QA can require them in the rewritten post.
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
    # choose for a public transport contract. These semantic fragments let exact
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
        # Only inspect the path local to the media candidate. Telegram's public
        # HTML keeps the channel/user-photo wrapper open around the whole message,
        # so using every ancestor makes every real attachment inherit
        # ``user_photo`` and look like chrome.
        folded = {str(item or "").casefold() for item in classes}
        safe_hints = ("grouped", "attachment", "gallery")
        return any(hint in cls for cls in folded for hint in safe_hints)

    def _handle_start(self, tag: str, attrs, *, self_closing: bool = False) -> None:
        # ``base.TelegramParser`` passes the union of *all* ancestor classes to
        # ``_add_media``. Current t.me/s markup has a persistent
        # ``tgme_widget_message_user_photo`` ancestor that wraps the message
        # bubble too, so that global union cannot be used for classification.
        # Keep only the media element plus its closest ancestor as the
        # candidate-local structural context. This still catches avatars,
        # replies, reactions and video thumbnails while avoiding unrelated
        # message-header chrome.
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        local = self._classes(values)
        path_local = set(local)
        for _, ancestor_classes in self.stack[-1:]:
            path_local.update(ancestor_classes)
        self._strict_candidate_classes = path_local

        # Current Telegram HTML sometimes lazy-loads video URLs outside ``src``.
        # Capture direct media attributes while the candidate still belongs to this
        # exact ``data-post`` widget. The base parser will still handle normal src.
        low_tag = tag.casefold()
        if self.current is not None:
            if self._contains_marker(path_local, self._DIRECT_CONTENT_MEDIA_MARKERS) and any(
                hint in cls.casefold() for cls in path_local for hint in ("video", "player")
            ):
                self.current["video_attachment_seen"] = 1
            direct_video = self._video_attr_url(values) if low_tag in {"video", "source", "a", "div"} else ""
            if direct_video and (low_tag in {"video", "source"} or direct_video.casefold().split("?",1)[0].endswith((".mp4", ".m4v", ".mov", ".webm"))):
                self._add_media("video", direct_video, path_local)
            poster = str(values.get("poster") or "").strip()
            if poster.startswith(("http://", "https://")):
                self._remember_video_poster(poster)

        # Telegram frequently renders operational links as ``<a href=...>посиланням</a>``.
        # The base parser keeps only visible text, which silently destroys the target.
        # Preserve the exact href inline while we are inside the real message text.
        # This is deliberately limited to http(s) anchors inside tgme_widget_message_text;
        # page chrome, author links and preview wrappers are outside that boundary.
        depth = len(self.stack) + 1
        href = values.get("href", "").strip()
        if (
            self.current is not None
            and tag.casefold() == "a"
            and self.text_depth is not None
            and depth >= self.text_depth
            and href.startswith(("http://", "https://"))
        ):
            parts = self.current.setdefault("text", [])
            assert isinstance(parts, list)
            current_text = "".join(str(part) for part in parts)
            if href not in current_text:
                parts.append(f" {href} ")

        try:
            super()._handle_start(tag, attrs, self_closing=self_closing)
        finally:
            self._strict_candidate_classes = set()

    def _remember_preview_fallback(self, kind: str, url: str) -> None:
        """Keep one exact-post preview candidate as a last-resort image.

        Municipal Telegram channels often publish a link card instead of attaching a
        separate photo. RC28 treated every link-preview image as chrome, which left
        required-media channels permanently empty. The preview still belongs to the
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

    def _remember_video_poster(self, url: str) -> None:
        """Preserve the exact post's own video poster as a last-resort visual.

        Public ``t.me/s`` pages often expose only the poster image for a video and
        omit the direct MP4 URL. Older code correctly rejected that poster as a
        *second* attachment when a video was available, but accidentally turned
        genuine video posts into text-only articles when the MP4 was lazy-loaded.
        The poster is therefore retained only as an exact-post fallback.
        """
        if self.current is None:
            return
        value = str(url or "").strip()
        if not value:
            return
        self.current["video_attachment_seen"] = 1
        key = media_identity("image", value)
        keys = self.current.setdefault("video_poster_keys", set())
        assert isinstance(keys, set)
        if key in keys:
            return
        keys.add(key)
        posters = self.current.setdefault("video_poster_candidates", [])
        assert isinstance(posters, list)
        posters.append(encode_media("image", value)[:3020])

    @staticmethod
    def _video_attr_url(values: dict[str, str]) -> str:
        for key in ("src", "data-src", "data-video", "data-video-src", "data-url", "data-file"):
            value = str(values.get(key) or "").strip()
            if value.startswith(("http://", "https://")):
                return value
        return ""

    def _add_media(self, kind: str, url: str, classes: set[str]) -> None:
        if self.current is None:
            return
        self.current["raw_media_candidates"] = int(self.current.get("raw_media_candidates") or 0) + 1

        local_classes = set(getattr(self, "_strict_candidate_classes", set()) or set())
        candidate_classes = local_classes or set(classes)

        if str(kind).casefold() == "image" and self._contains_marker(candidate_classes, self._VIDEO_THUMB_MARKERS):
            self.current["discarded_video_thumb"] = int(self.current.get("discarded_video_thumb") or 0) + 1
            self._remember_video_poster(url)
            return

        hard_markers = set(self._NON_CONTENT_MEDIA_MARKERS) - set(self._SOFT_PREVIEW_MARKERS)
        if self._contains_marker(candidate_classes, hard_markers):
            self.current["discarded_non_content"] = int(self.current.get("discarded_non_content") or 0) + 1
            return

        direct_content = (
            self._contains_marker(candidate_classes, self._DIRECT_CONTENT_MEDIA_MARKERS)
            or self._generic_direct_content(candidate_classes)
        )
        soft_preview = self._contains_marker(candidate_classes, self._SOFT_PREVIEW_MARKERS)
        if not direct_content and soft_preview:
            self._remember_preview_fallback(kind, url)
            self.current["discarded_non_content"] = int(self.current.get("discarded_non_content") or 0) + 1
            return

        value = str(url or "").strip()
        if not value:
            return
        if str(kind).casefold() == "video":
            self.current["video_recovery"] = "direct_video"
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
        # Direct source media always wins. If the exact Telegram widget contains no
        # direct attachment, allow a single exact-post link-preview image. Never
        # stitch from a neighbouring data-post, so the ownership boundary remains
        # deterministic.
        if self.current is not None:
            media = self.current.setdefault("media", [])
            posters = self.current.get("video_poster_candidates")
            previews = self.current.get("preview_media_candidates")
            if isinstance(media, list) and not media and isinstance(posters, list) and posters:
                # RC69: a video poster is evidence that the source owns a VIDEO, not
                # a legitimate replacement for that video. Keep the poster only as
                # diagnostic/retry metadata. Publishing a screenshot in place of a
                # playable source video is a media-integrity failure.
                self.current["video_poster_fallback_used"] = 1
                self.current["video_recovery"] = "poster_fallback"
            if (
                isinstance(media, list) and not media
                and not bool(self.current.get("video_attachment_seen"))
                and isinstance(previews, list) and previews
            ):
                media.append(str(previews[0]))
                self.current["preview_fallback_used"] = 1
        super()._finish()


def _upgrade_strict_article(username: str, article: CollectedArticle, entry_by_id: dict[int, base.TelegramEntry]) -> CollectedArticle:
    """Annotate a source-owned Telegram article after deterministic adjacency stitching.

    RC67 accidentally replaced the mature text+adjacent-media ownership rule with
    "one data-post == one article". Municipal channels often post caption/text and
    then the media as the immediately following Telegram message. RC69 restores
    that bounded ownership rule: only consecutive message IDs within the existing
    five-minute adjacency window may be joined. No arbitrary neighbour donates media.
    """
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
    tg["media_filter_version"] = 7
    tg["stitch_policy"] = "adjacent_media_only_v2"

    mids = tg.get("message_ids") if isinstance(tg.get("message_ids"), list) else []
    group = [entry_by_id.get(int(mid)) for mid in mids if str(mid).isdigit()]
    group = [entry for entry in group if entry is not None]
    modes = [str(getattr(entry, "video_recovery", "") or "") for entry in group]
    if "exact_post_video" in modes:
        mode = "exact_post_video"
    elif "direct_video" in modes:
        mode = "direct_video"
    elif "poster_fallback" in modes:
        mode = "poster_fallback"
    elif "no_video" in modes:
        mode = "no_video"
    else:
        mode = ""
    tg["video_recovery"] = mode
    tg["video_attachment_seen"] = any(bool(getattr(entry, "video_attachment_seen", False)) for entry in group)
    posters = [str(getattr(entry, "video_poster_url", "") or "") for entry in group]
    posters = [value for value in posters if value]
    if posters:
        # Metadata only. Never merge this into article.media_urls.
        tg["video_poster_url"] = posters[0]

    article.article_layout_json = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
    return article


def _strict_media_bearing(entry: base.TelegramEntry) -> bool:
    """Treat a confirmed Telegram video placeholder as media-bearing for stitching.

    Telegram may expose a video marker/poster without the MP4 URL. RC69 correctly
    stopped publishing the poster as a fake replacement, but that left video-only
    messages as ``text==""`` and ``media==[]``. The base stitcher then discarded
    them before they could be attached to the adjacent caption/text message.

    A placeholder is *not* publishable media. It only participates in ownership
    stitching so the combined article carries ``video_attachment_seen`` and is
    blocked later with TELEGRAM_VIDEO_PENDING until the real video is recovered.
    """
    if bool(entry.media):
        return True
    if bool(getattr(entry, "video_attachment_seen", False)):
        return True
    return str(getattr(entry, "video_recovery", "") or "") in {
        "direct_video", "exact_post_video", "poster_fallback", "no_video"
    }


def strict_stitch_telegram(username: str, entries: list[base.TelegramEntry]) -> list[CollectedArticle]:
    """Build articles only from the exact Telegram post that owns the text/media.

    Adjacent message IDs are not ownership evidence. Older stitching could attach a
    media-only post N to text post N+1 merely because they were close in time, which
    risks publishing another post's image/video. The strict pipeline now keeps
    exact-post boundaries absolute; albums already exposed inside one Telegram widget
    stay attached to that entry.
    """
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

    articles: list[CollectedArticle] = []
    for entry in ordered:
        if not str(entry.text or "").strip():
            # A media-only neighbour is never borrowed by another post. It can be
            # reconsidered on a later exact-post fetch if Telegram exposes text.
            continue
        article = base._to_article(username, entry, [])
        articles.append(article)

    return [_upgrade_strict_article(username, article, entry_by_id) for article in articles]

def _entry_has_video(entry: base.TelegramEntry) -> bool:
    from ..media import decode_media
    for encoded in entry.media:
        try:
            kind, _ = decode_media(encoded)
        except Exception:
            continue
        if kind == "video":
            return True
    return False


def _hydrate_exact_video_post(username: str, entry: base.TelegramEntry) -> base.TelegramEntry:
    """Resolve the exact Telegram video outcome and emit one explicit telemetry event.

    Modes are intentionally transport-level and channel-agnostic:
    ``direct_video`` (already present on t.me/s), ``exact_post_video`` (recovered
    from the exact embed), ``poster_fallback`` (same-post visual only), or
    ``no_video`` (Telegram exposed a video marker but no usable media).
    """
    post_id = base._post_number(entry.post)
    if post_id is None:
        return entry
    source_url = f"https://t.me/{username}/{post_id}"

    if _entry_has_video(entry):
        entry.video_recovery = str(getattr(entry, "video_recovery", "") or "direct_video")
        event(
            "ingest", "telegram video recovery outcome", source=username, post_id=post_id,
            source_url=source_url, mode=entry.video_recovery, media_count=len(entry.media),
            discarded_video_thumb=int(getattr(entry, "discarded_video_thumb", 0) or 0),
        )
        return entry

    if int(getattr(entry, "discarded_video_thumb", 0) or 0) <= 0:
        return entry

    try:
        response = collector._source_fetch(
            f"https://t.me/{username}/{post_id}?embed=1&mode=tme",
            max_bytes=8 * 1024 * 1024,
            allowed_content_types={"text/html", "application/xhtml+xml"},
            timeout=20,
        )
        parser = StrictTelegramParser(username)
        parser.feed(response.body.decode("utf-8", errors="replace"))
        parser.close()
        exact = next((x for x in parser.entries if base._post_number(x.post) == post_id), None)
        if exact is None and len(parser.entries) == 1:
            exact = parser.entries[0]
        if exact is not None and _entry_has_video(exact):
            if not exact.text:
                exact.text = entry.text
            if not exact.published:
                exact.published = entry.published
            exact.video_recovery = "exact_post_video"
            event(
                "ingest", "telegram video recovery outcome", source=username, post_id=post_id,
                source_url=source_url, mode="exact_post_video", media_count=len(exact.media),
                discarded_video_thumb=int(getattr(entry, "discarded_video_thumb", 0) or 0),
            )
            return exact
    except Exception as exc:
        event(
            "ingest", "telegram exact video hydration failed", level=30, source=username,
            post_id=post_id, source_url=source_url, detail=str(exc)[:500],
        )

    if str(getattr(entry, "video_poster_url", "") or ""):
        # Poster exists, but RC69 deliberately keeps it out of source media. It is
        # useful evidence/retry metadata, not a substitute for the original video.
        entry.video_recovery = "poster_fallback"
        mode = "poster_fallback"
    else:
        entry.video_recovery = "no_video"
        mode = "no_video"
    event(
        "ingest", "telegram video recovery outcome",
        level=30 if mode == "no_video" else 20,
        source=username, post_id=post_id, source_url=source_url, mode=mode,
        media_count=len(entry.media),
        discarded_video_thumb=int(getattr(entry, "discarded_video_thumb", 0) or 0),
    )
    return entry


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
    entries = [_hydrate_exact_video_post(username, entry) for entry in parser.entries]
    items = strict_stitch_telegram(username, entries)
    if not items:
        raise collector.CollectorError("Не вдалося прочитати Telegram-канал")
    return items[-40:]


def collect_strict(source: Source, *, page_prefer_feed: bool=False, page_candidate_scan_limit: int=24, page_fetch_limit: int=8) -> list[CollectedArticle]:
    return collect_telegram_strict(source) if source.kind == "telegram" else collector.collect_source(
        source, page_prefer_feed=page_prefer_feed, page_candidate_scan_limit=page_candidate_scan_limit, page_fetch_limit=page_fetch_limit
    )


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
