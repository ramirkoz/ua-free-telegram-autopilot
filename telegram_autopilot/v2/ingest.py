from __future__ import annotations

import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable

from .. import collector
from ..database import content_hash
from ..media import encode_media, media_identity
from ..models import CollectedArticle, Source
from .loghub import event
from .storage import V2Store


@dataclass(slots=True)
class TelegramEntry:
    post: str
    text: str
    published: str | None
    media: list[str]=field(default_factory=list)
    forwarded: bool=False
    forwarded_from: str=""
    raw_media_candidates: int=0
    discarded_non_content: int=0
    discarded_video_thumb: int=0
    discarded_duplicate: int=0


class TelegramParser(HTMLParser):
    """Parse public ``t.me/s`` HTML without treating Telegram chrome as post media.

    Telegram renders the channel avatar as an ``<img>`` *inside* an ancestor whose
    class is ``tgme_widget_message_user_photo``.  RC17 checked only the media tag's
    own class, so that avatar became a real attachment.  Video posters are exposed
    as background images under ``*_video_thumb`` and must never be published as a
    second photo next to the actual video.
    """

    _VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
    _NON_CONTENT_MEDIA_MARKERS = {
        "tgme_widget_message_user_photo",
        "tgme_widget_message_author_photo",
        "tgme_widget_message_reaction",
        "tgme_widget_message_link_preview",
        "tgme_widget_message_webpage",
        "link_preview_image",
        "reply_thumb",
        "reply_photo",
        "forwarded_from_photo",
        "emoji",
        "reaction",
        "avatar",
        "profile_photo",
        "user_photo",
        "author_photo",
    }
    _VIDEO_THUMB_MARKERS = {
        "tgme_widget_message_video_thumb",
        "video_thumb",
        "video_poster",
    }

    def __init__(self, username: str):
        super().__init__(convert_charrefs=True)
        self.username = username
        self.stack: list[tuple[str, set[str]]] = []
        self.message_depth: int | None = None
        self.text_depth: int | None = None
        self.forward_depth: int | None = None
        self.current: dict[str, object] | None = None
        self.entries: list[TelegramEntry] = []

    @staticmethod
    def _classes(attrs: dict[str, str]) -> set[str]:
        return {x for x in attrs.get("class", "").split() if x}

    def _ancestor_classes(self) -> set[str]:
        out: set[str] = set()
        for _, classes in self.stack:
            out.update(classes)
        return out

    @staticmethod
    def _contains_marker(classes: set[str], markers: set[str]) -> bool:
        folded = {str(c).casefold() for c in classes}
        return any(marker in cls for cls in folded for marker in markers)

    def _add_media(self, kind: str, url: str, classes: set[str]) -> None:
        if self.current is None:
            return
        self.current["raw_media_candidates"] = int(self.current.get("raw_media_candidates") or 0) + 1
        if self._contains_marker(classes, self._NON_CONTENT_MEDIA_MARKERS):
            self.current["discarded_non_content"] = int(self.current.get("discarded_non_content") or 0) + 1
            return
        if str(kind).casefold() == "image" and self._contains_marker(classes, self._VIDEO_THUMB_MARKERS):
            self.current["discarded_video_thumb"] = int(self.current.get("discarded_video_thumb") or 0) + 1
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

    def _handle_start(self, tag: str, attrs, *, self_closing: bool=False) -> None:
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        classes = self._classes(values)
        tag = tag.casefold()
        depth = len(self.stack) + 1
        all_classes = self._ancestor_classes() | classes

        if tag == "div" and "tgme_widget_message" in classes and values.get("data-post"):
            self._finish()
            self.current = {
                "post": values["data-post"], "text": [], "published": None,
                "media": [], "media_keys": set(), "forwarded": False, "forward_parts": [],
                "raw_media_candidates": 0, "discarded_non_content": 0,
                "discarded_video_thumb": 0, "discarded_duplicate": 0,
            }
            self.message_depth = depth

        if self.current is not None:
            if "tgme_widget_message_text" in classes:
                self.text_depth = depth
            if any("forwarded" in c.casefold() for c in classes):
                self.current["forwarded"] = True
                if self.forward_depth is None:
                    self.forward_depth = depth
            if self.current.get("forwarded"):
                origin = values.get("title") or values.get("data-peer") or ""
                if origin:
                    parts = self.current.setdefault("forward_parts", [])
                    assert isinstance(parts, list)
                    parts.append(origin)
            if tag == "time" and values.get("datetime"):
                self.current["published"] = values["datetime"]
            if tag == "img" and values.get("src"):
                self._add_media("image", values["src"], all_classes)
            if tag in {"video", "source"} and values.get("src"):
                self._add_media("video", values["src"], all_classes)
            style = values.get("style", "")
            if style:
                match = re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)", style, flags=re.I)
                if match:
                    self._add_media("image", match.group(1), all_classes)

        if not self_closing and tag not in self._VOID_TAGS:
            self.stack.append((tag, classes))

    def handle_starttag(self, tag: str, attrs):
        self._handle_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs):
        self._handle_start(tag, attrs, self_closing=True)

    def handle_data(self, data: str):
        if self.current is None:
            return
        depth = len(self.stack)
        if self.text_depth is not None and depth >= self.text_depth:
            parts = self.current.setdefault("text", [])
            assert isinstance(parts, list)
            parts.append(data)
        if self.forward_depth is not None and depth >= self.forward_depth:
            parts = self.current.setdefault("forward_parts", [])
            assert isinstance(parts, list)
            parts.append(data)

    def handle_endtag(self, tag: str):
        tag = tag.casefold()
        depth = len(self.stack)
        if self.current is not None and self.text_depth == depth:
            self.text_depth = None
        if self.current is not None and self.forward_depth == depth:
            self.forward_depth = None
        if self.current is not None and self.message_depth == depth and tag == "div":
            self._finish()

        # Public Telegram HTML is normally balanced, but tolerate malformed fragments
        # by removing up to the closest matching open tag.
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx][0] == tag:
                del self.stack[idx:]
                break

    def close(self):
        super().close()
        self._finish()
        self.stack.clear()

    def _finish(self):
        if not self.current:
            return
        post = str(self.current.get("post") or "").strip()
        text_parts = self.current.get("text")
        text = " ".join("".join(text_parts if isinstance(text_parts, list) else []).split())
        media_obj = self.current.get("media")
        media = list(media_obj)[:24] if isinstance(media_obj, list) else []
        fwd_obj = self.current.get("forward_parts")
        forwarded_from = " ".join(" ".join(fwd_obj if isinstance(fwd_obj, list) else []).split())[:500]
        if post and (text or media):
            self.entries.append(TelegramEntry(
                post=post,
                text=text,
                published=str(self.current.get("published") or "") or None,
                media=media,
                forwarded=bool(self.current.get("forwarded")),
                forwarded_from=forwarded_from,
                raw_media_candidates=int(self.current.get("raw_media_candidates") or 0),
                discarded_non_content=int(self.current.get("discarded_non_content") or 0),
                discarded_video_thumb=int(self.current.get("discarded_video_thumb") or 0),
                discarded_duplicate=int(self.current.get("discarded_duplicate") or 0),
            ))
        self.current = None
        self.message_depth = self.text_depth = self.forward_depth = None

def _post_number(post: str) -> int | None:
    try:
        tail=str(post or "").rsplit("/",1)[-1]; return int(tail) if tail.isdigit() else None
    except Exception: return None


def _entry_dt(entry: TelegramEntry) -> datetime | None:
    try:
        dt=datetime.fromisoformat(str(entry.published or "").replace("Z","+00:00"));
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception: return None


def _adjacent(a: TelegramEntry,b: TelegramEntry,seconds: int=300) -> bool:
    ai,bi=_post_number(a.post),_post_number(b.post)
    if ai is not None and bi is not None and bi!=ai+1: return False
    ad,bd=_entry_dt(a),_entry_dt(b)
    if ad is not None and bd is not None: return 0<=(bd-ad).total_seconds()<=seconds
    return ai is not None and bi is not None and bi==ai+1


def _held(entry: TelegramEntry) -> bool:
    if entry.media or not entry.text: return False
    dt=_entry_dt(entry)
    return bool(dt and 0 <= (datetime.now(timezone.utc)-dt).total_seconds() <= 180)


def _to_article(username: str, primary: TelegramEntry, attached: list[TelegramEntry]) -> CollectedArticle:
    # A source can publish media-only and text-only Telegram messages back-to-back.
    # Treat that pair as one logical article, preserving chronological media order.
    group = [primary, *attached]
    group.sort(key=lambda e: (_post_number(e.post) is None, _post_number(e.post) or 0, e.post))
    media: list[str] = []
    seen_media: set[str] = set()
    from ..media import decode_media
    for entry in group:
        for encoded in entry.media:
            try:
                kind, url = decode_media(encoded)
            except Exception:
                continue
            key = media_identity(kind, url)
            if key in seen_media:
                continue
            seen_media.add(key)
            media.append(encode_media(kind, url))
    message_ids = [str(_post_number(e.post) or e.post.rsplit("/", 1)[-1]) for e in group]
    forwarded_from = " | ".join(dict.fromkeys(e.forwarded_from for e in group if e.forwarded_from))[:800]
    blocks = []
    for idx, encoded in enumerate(media[:24], 1):
        try:
            kind, url = decode_media(encoded)
        except Exception:
            continue
        if kind in {"image", "video"} and url:
            blocks.append({
                "type": "media", "index": idx, "kind": kind, "url": url,
                "caption": "", "alt": "", "context": primary.text[:700],
                "position": min(.35, .03 + idx * .02),
            })
    raw_candidates = sum(int(e.raw_media_candidates or 0) for e in group)
    discarded_non_content = sum(int(e.discarded_non_content or 0) for e in group)
    discarded_video_thumb = sum(int(e.discarded_video_thumb or 0) for e in group)
    discarded_duplicate = sum(int(e.discarded_duplicate or 0) for e in group)
    layout = json.dumps({
        "version": 4,
        "source_kind": "telegram",
        "telegram": {
            "source_username": username,
            "message_ids": message_ids,
            "forwarded": any(e.forwarded for e in group),
            "forwarded_from": forwarded_from,
            "stitched": len(group) > 1,
            "media_count": len(media),
            "media_group": len(media) >= 2,
            "media_identity_version": 2,
            "media_filter_version": 2,
            "media_filter": {
                "raw_candidates": raw_candidates,
                "discarded_non_content": discarded_non_content,
                "discarded_video_thumb": discarded_video_thumb,
                "discarded_duplicate": discarded_duplicate,
                "content_media": len(media),
            },
            "delivery_hint": "caption_on_media",
        },
        "blocks": blocks,
    }, ensure_ascii=False, separators=(",", ":"))
    title = primary.text[:220] + ("…" if len(primary.text) > 220 else "")
    url = "https://t.me/" + primary.post
    return CollectedArticle(primary.post[:1000], title or "Telegram", url, primary.text, primary.published, media[:24], layout)


def stitch_telegram(username: str, entries: list[TelegramEntry]) -> list[CollectedArticle]:
    # Public Telegram HTML ordering has changed in the past.  Work chronologically
    # instead of trusting DOM order so media-only + text-only adjacency is stable.
    ordered = list(entries)
    ordered.sort(key=lambda e: (
        _post_number(e.post) is None,
        _post_number(e.post) if _post_number(e.post) is not None else 10**18,
    ))
    result: list[CollectedArticle] = []
    i = 0
    while i < len(ordered):
        current = ordered[i]
        if not current.text and current.media:
            run = [current]
            j = i + 1
            while j < len(ordered) and not ordered[j].text and ordered[j].media and _adjacent(run[-1], ordered[j]):
                run.append(ordered[j]); j += 1
            if j < len(ordered) and ordered[j].text and _adjacent(run[-1], ordered[j]):
                primary = ordered[j]
                attached = run[:]
                k = j + 1
                # Also accept media-only continuation immediately after the text.
                previous = primary
                while k < len(ordered) and not ordered[k].text and ordered[k].media and _adjacent(previous, ordered[k]):
                    attached.append(ordered[k]); previous = ordered[k]; k += 1
                result.append(_to_article(username, primary, attached))
                i = k
                continue
            # Do not publish a media-only orphan as a textless article. It remains
            # visible on the next public page fetch and can be stitched when text arrives.
            i = j
            continue
        if current.text:
            attached: list[TelegramEntry] = []
            j = i + 1
            previous = current
            while j < len(ordered) and not ordered[j].text and ordered[j].media and _adjacent(previous, ordered[j]):
                attached.append(ordered[j]); previous = ordered[j]; j += 1
            if not current.media and not attached and j >= len(ordered) and _held(current):
                # Fresh final text-only messages are briefly held so a following
                # media-only message can arrive and be combined on the next poll.
                i = j
                continue
            result.append(_to_article(username, current, attached))
            i = j
            continue
        i += 1
    return result


def collect_telegram(source: Source) -> list[CollectedArticle]:
    username=collector._telegram_username(source.url)
    if not username: raise collector.CollectorError("Telegram-джерело має містити публічну адресу t.me/username")
    response=collector._source_fetch(f"https://t.me/s/{username}",max_bytes=8*1024*1024,allowed_content_types={"text/html","application/xhtml+xml"},timeout=35)
    parser=TelegramParser(username); parser.feed(response.body.decode("utf-8",errors="replace")); parser.close(); items=stitch_telegram(username,parser.entries)
    if not items: raise collector.CollectorError("Не вдалося прочитати Telegram-канал")
    return items[-40:]


def collect(source: Source) -> list[CollectedArticle]:
    return collect_telegram(source) if source.kind=="telegram" else collector.collect_source(source)


# Three fetches per channel are enough to collapse long sequential collection cycles
# without turning 126 sources into a denial-of-service against the user's network.
# The global semaphore caps all channel collectors together at six live source fetches.
_GLOBAL_SOURCE_FETCH_LIMIT = threading.BoundedSemaphore(6)


class IngestService:
    def __init__(self,store: V2Store): self.store=store
    def collect_channel(self,channel_id: int, heartbeat: Callable[[], None] | None = None) -> dict[str,int]:
        added=seen=errors=skipped=0

        def beat() -> None:
            if heartbeat is not None:
                try: heartbeat()
                except Exception: pass

        sources: list[Source] = []
        for row in self.store.sources_for_channel(channel_id,enabled_only=True):
            beat()
            source=Source(id=int(row["id"]),channel_id=int(row["channel_id"]),kind=str(row["kind"]),name=str(row["name"]),url=str(row["url"]),enabled=bool(row["enabled"]),initialized=bool(row["initialized"]),last_checked_at=str(row["last_checked_at"] or "") or None,last_error=str(row["last_error"] or "") or None,priority=int(row["priority"] or 100))
            cooling, cooldown_until = self.store.source_cooldown_active(source.id)
            if cooling:
                skipped += 1
                event("ingest","source cooldown skip",channel_id=channel_id,source_id=source.id,source=source.name,cooldown_until=cooldown_until)
                continue
            sources.append(source)

        def fetch_one(source: Source) -> tuple[list[CollectedArticle], int]:
            started=time.monotonic()
            with _GLOBAL_SOURCE_FETCH_LIMIT:
                items=collect(source)
            return items, int(max(0.0,time.monotonic()-started)*1000)

        max_workers=max(1,min(3,len(sources)))
        with ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix=f"ingest-{channel_id}") as pool:
            future_map={pool.submit(fetch_one,source): (source,time.monotonic()) for source in sources}
            for future in as_completed(future_map):
                source, submitted_at=future_map[future]
                beat()
                try:
                    items,duration_ms=future.result(); seen+=len(items)
                    source_added=0
                    # SQLite writes remain serialized in this collector thread. Only the
                    # network-bound source fetch is parallelized.
                    for item in items:
                        media_json=json.dumps(list(item.media_urls or []),ensure_ascii=False,separators=(",",":"))
                        before=self._existing(channel_id,source.id,item.external_id,item.url)
                        self.store.insert_collected(channel_id=channel_id,source_id=source.id,external_id=item.external_id,title=item.title,source_url=item.url,raw_text=item.raw_text,content_hash=content_hash(item.title,item.raw_text),source_published_at=str(item.published_at or ""),media_json=media_json,article_layout_json=str(item.article_layout_json or "{}"))
                        if not before:
                            added+=1; source_added+=1
                        beat()
                    self.store.record_source_success(source.id,duration_ms)
                    with self.store.connect() as con: con.execute("UPDATE sources SET initialized=1,last_checked_at=?,last_error='' WHERE id=?",(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),source.id))
                    event("ingest","source collected",channel_id=channel_id,source_id=source.id,source=source.name,items=len(items),added=source_added,duration_ms=duration_ms)
                except Exception as exc:
                    errors+=1
                    duration_ms=int(max(0.0,time.monotonic()-submitted_at)*1000)
                    failures,cooldown=self.store.record_source_failure(source.id,duration_ms,str(exc))
                    with self.store.connect() as con: con.execute("UPDATE sources SET last_checked_at=?,last_error=? WHERE id=?",(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),str(exc)[:1200],source.id))
                    event("ingest","source collection failed",level=40,channel_id=channel_id,source_id=source.id,source=source.name,detail=str(exc)[:600],duration_ms=duration_ms,consecutive_failures=failures,cooldown_until=cooldown)
                finally:
                    beat()
        return {"seen":seen,"added":added,"errors":errors,"skipped_cooldown":skipped}
    def _existing(self,channel_id: int,source_id: int,external_id: str,url: str) -> bool:
        with self.store.connect() as con:
            if con.execute("SELECT 1 FROM articles WHERE source_id=? AND external_id=?",(int(source_id),str(external_id))).fetchone() is not None:
                return True
        return self.store.find_equivalent_article(int(channel_id),str(url or "")) is not None

