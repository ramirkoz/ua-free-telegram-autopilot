"""Fail-closed exact-source video preflight for text-only Telegram publications.

A preferred-media channel may post genuine text-only news. It must not silently
strip a Telegram video because public /s/ listing did not expose the attachment.
Check only the *same* source channel+post, never a neighbour or forward.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from .. import collector
from ..media import decode_media, valid_public_media
from .strict_ingest import StrictTelegramParser


@dataclass(frozen=True)
class ExactTelegramMediaCheck:
    outcome: str  # text_only | video_recovered | video_pending | uncertain
    video_media: tuple[str, ...] = ()
    reason: str = ""
    video_signal: str = ""


class _ExactPostVideoSignals(HTMLParser):
    """Inspect media markup only within the requested data-post bubble."""

    def __init__(self, post: str):
        super().__init__(convert_charrefs=True)
        self.post = post.casefold()
        self.depth = 0
        self.stack_depth = 0
        self.found = False
        self.signal = ""
        self.hits = 0

    def handle_starttag(self, tag, attrs):
        vals = {str(k).casefold(): str(v or "") for k, v in attrs}
        classes = vals.get("class", "").casefold()
        if tag == "div" and "tgme_widget_message" in classes.split() and vals.get("data-post", "").casefold() == self.post:
            self.depth = 1
            self.found = True
            self.stack_depth = 0
        elif self.depth:
            self.depth += 1 if tag not in {"img", "source", "meta", "br", "input", "link"} else 0
        if not self.depth:
            return
        # Structural video evidence in the exact widget, never plain text
        # mentioning video or media belonging to another data-post.
        cls_tokens = classes.split()
        if tag in {"video", "source"}:
            self.signal = self.signal or "html_video_tag"
        elif any(("message_video" in c or "video_player" in c or "video_thumb" in c or c in {"js-message_video", "video-js"}) for c in cls_tokens):
            self.signal = self.signal or "html_video_class"
        elif any(key in vals for key in ("data-video", "data-video-src", "data-video-id", "data-video-url")):
            self.signal = self.signal or "html_video_data"
        self.hits += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.depth and tag not in {"img", "source", "meta", "br", "input", "link"}:
            self.depth = max(0, self.depth - 1)


def _exact_telegram_identity(source_url: str) -> tuple[str, int] | None:
    parsed = urlparse(str(source_url or ""))
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").casefold() not in {"t.me", "www.t.me", "telegram.me"}:
        return None
    match = re.fullmatch(r"/([A-Za-z0-9_]{3,32})/(\d+)", parsed.path.rstrip("/"))
    if not match:
        return None
    return match.group(1), int(match.group(2))


def check_exact_telegram_video(source_url: str, *, timeout: float = 12.0) -> ExactTelegramMediaCheck:
    identity = _exact_telegram_identity(source_url)
    if identity is None:
        return ExactTelegramMediaCheck("uncertain", reason="invalid_exact_source_url")
    username, post_id = identity
    url = f"https://t.me/{username}/{post_id}?embed=1&mode=tme"
    try:
        response = collector._source_fetch(
            url, max_bytes=4 * 1024 * 1024,
            allowed_content_types={"text/html", "application/xhtml+xml"},
            timeout=timeout,
        )
        html = response.body.decode("utf-8", errors="replace")
        parser = StrictTelegramParser(username)
        parser.feed(html)
        parser.close()
        exact = next((e for e in parser.entries if e.post.casefold() == f"{username}/{post_id}".casefold()), None)
        signals = _ExactPostVideoSignals(f"{username}/{post_id}")
        signals.feed(html)
        signals.close()
        if exact is None or not signals.found:
            return ExactTelegramMediaCheck("uncertain", reason="exact_post_not_in_embed")
        videos = []
        for encoded in exact.media:
            kind, url = decode_media(encoded)
            candidate = valid_public_media(encoded)
            if kind == "video" and candidate and candidate[0] == "video" and encoded not in videos:
                videos.append(encoded)
        if videos:
            return ExactTelegramMediaCheck("video_recovered", tuple(videos), video_signal=signals.signal or "video_url")
        if signals.signal or exact.video_attachment_seen or exact.discarded_video_thumb:
            return ExactTelegramMediaCheck("video_pending", reason="video_evidence_without_uploadable_file", video_signal=signals.signal or "parser_video_marker")
        return ExactTelegramMediaCheck("text_only", reason="exact_post_contains_no_video")
    except Exception as exc:
        return ExactTelegramMediaCheck("uncertain", reason=f"exact_post_fetch_failed: {type(exc).__name__}: {str(exc)[:180]}")


# 2.2.7: photo and album parity on the same exact Telegram data-post.
# Video-only checks above remain backward compatible with 2.2.6 regressions.
@dataclass(frozen=True)
class ExactTelegramSourceMedia:
    outcome: str  # confirmed | text_only | photo_pending | video_pending | uncertain
    media: tuple[str, ...] = ()
    expected_photos: int = 0
    video_expected: bool = False
    reason: str = ""
    photo_signal: str = ""
    video_signal: str = ""


class _ExactPostPhotoSignals(HTMLParser):
    """Only direct photo/grouped wrappers within the requested message.

    Avatars, link cards, photo captions, reactions, and neighboring data-post
    widgets are not structural evidence of an attached source image.
    """

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, post: str):
        super().__init__(convert_charrefs=True)
        self.post = post.casefold()
        self.depth = 0
        self.found = False
        self.wraps = 0
        self.images = 0
        self.grouped_photos = 0

    def handle_starttag(self, tag, attrs):
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        classes = set(values.get("class", "").casefold().split())
        if tag == "div" and "tgme_widget_message" in classes and values.get("data-post"):
            self.depth = 1 if values["data-post"].casefold() == self.post else 0
            self.found = self.found or bool(self.depth)
            return
        if not self.depth:
            return
        if "tgme_widget_message_photo_wrap" in classes or "js-message_photo" in classes:
            self.wraps += 1
        elif "tgme_widget_message_photo" in classes:
            self.images += 1
        elif "tgme_widget_message_grouped_layer" in classes and "tgme_widget_message_video_player" not in classes:
            self.grouped_photos += 1
        if tag not in self._VOID:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.depth and tag not in self._VOID:
            self.depth -= 1

    @property
    def expected_photos(self) -> int:
        # Some Telegram layouts nest photo and grouped wrappers around the same
        # asset; use the maximum category count rather than adding them.
        return max(self.wraps, self.images, self.grouped_photos)

    @property
    def signal(self) -> str:
        return "photo_wrap" if self.wraps else ("message_photo" if self.images else (
            "grouped_layer" if self.grouped_photos else ""))


def check_exact_telegram_media(source_url: str, *, timeout: float = 12.0) -> ExactTelegramSourceMedia:
    """Read one precise public Telegram post for photo, album and video parity.

    No nearby messages, forwarded author avatars or article-related stock images.
    An unreachable embed is uncertain, never evidence that the source is text-only.
    """
    identity = _exact_telegram_identity(source_url)
    if identity is None:
        return ExactTelegramSourceMedia("uncertain", reason="invalid_exact_source_url")
    username, post_id = identity
    try:
        response = collector._source_fetch(
            f"https://t.me/{username}/{post_id}?embed=1&mode=tme",
            max_bytes=4 * 1024 * 1024,
            allowed_content_types={"text/html", "application/xhtml+xml"},
            timeout=timeout,
        )
        html = response.body.decode("utf-8", errors="replace")
        parser = StrictTelegramParser(username)
        parser.feed(html)
        parser.close()
        exact = next((e for e in parser.entries
                      if e.post.casefold() == f"{username}/{post_id}".casefold()), None)
        photos = _ExactPostPhotoSignals(f"{username}/{post_id}")
        photos.feed(html)
        photos.close()
        videos = _ExactPostVideoSignals(f"{username}/{post_id}")
        videos.feed(html)
        videos.close()
        if exact is None or not (photos.found and videos.found):
            return ExactTelegramSourceMedia("uncertain", reason="exact_post_not_in_embed")
        media = []
        for raw in exact.media:
            if valid_public_media(raw) and raw not in media:
                media.append(raw)
        photo_count = sum(1 for raw in media if decode_media(raw)[0] == "image")
        video_count = sum(1 for raw in media if decode_media(raw)[0] == "video")
        video_signal = videos.signal or (
            "parser_video_marker" if exact.video_attachment_seen or exact.discarded_video_thumb else "")
        video_expected = bool(video_signal or video_count)
        expected_photos = max(photos.expected_photos, photo_count)
        if video_expected and not video_count:
            return ExactTelegramSourceMedia(
                "video_pending", tuple(media), expected_photos, True,
                "original_video_unavailable", photos.signal, video_signal)
        if expected_photos > photo_count:
            return ExactTelegramSourceMedia(
                "photo_pending", tuple(media), expected_photos, video_expected,
                "original_photo_or_album_incomplete", photos.signal, video_signal)
        if media:
            return ExactTelegramSourceMedia(
                "confirmed", tuple(media), expected_photos, video_expected,
                "exact_post_media_confirmed", photos.signal, video_signal)
        return ExactTelegramSourceMedia("text_only", reason="exact_post_no_attachment")
    except Exception as exc:
        return ExactTelegramSourceMedia(
            "uncertain", reason=f"exact_post_fetch_failed: {type(exc).__name__}: {str(exc)[:180]}")


def source_media_shortfall(check: ExactTelegramSourceMedia, encoded_items: list[str] | tuple[str, ...]) -> str:
    """Post-recovery guard: do not downgrade confirmed photo/video attachments."""
    counts = {"image": 0, "video": 0}
    for encoded in encoded_items:
        valid = valid_public_media(str(encoded))
        if valid and valid[0] in counts:
            counts[valid[0]] += 1
    if check.video_expected and counts["video"] == 0:
        return "TELEGRAM_VIDEO_PENDING"
    if check.expected_photos > counts["image"]:
        return "TELEGRAM_PHOTO_PENDING"
    return ""
