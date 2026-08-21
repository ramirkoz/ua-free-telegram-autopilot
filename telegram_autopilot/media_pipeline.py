from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from .media import valid_public_media
from .network import NetworkError, fetch_url

_MEDIA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_HARD_REJECT = (
    "advertisement", "advertorial", "sponsored", "sponsor", "affiliate", "promo", "promotion",
    "cocoon ai", "ai summary", "ai-summary", "newsletter", "subscribe", "outbrain", "taboola",
    "doubleclick", "googlesyndication", "googleadservices", "amazon-adsystem", "adserver", "ad-unit",
    "ad_slot", "ad-slot", "banner", "tracking", "pixel.gif", "1x1.gif", "favicon", "sprite",
    "avatar", "headshot", "profile-photo", "social-share", "share-icon", "analytics",
    "click to follow", "follow us", "follow on google", "google news", "follow tom's hardware",
)
_LOGO_WORDS = ("logo", "wordmark", "brandmark", "app-icon", "site-icon", "badge")
_STOP = {
    "this", "that", "with", "from", "have", "will", "into", "about", "after", "before", "their", "there",
    "what", "when", "where", "which", "your", "than", "over", "under", "more", "most", "news", "image",
    "photo", "Фото", "зображення", "для", "про", "який", "яка", "яке", "вони", "було", "після", "через",
}


@dataclass(slots=True)
class PreparedMedia:
    index: int
    kind: str
    url: str
    caption: str = ""
    alt: str = ""
    position: float = 0.0
    featured: bool = False
    mime_type: str = ""
    width: int = 0
    height: int = 0
    digest: str = ""
    data: bytes = b""
    context: str = ""
    classification: str = "unknown"
    relevance_score: float = 0.0

    @property
    def filename(self) -> str:
        path = urlsplit(self.url).path.rsplit("/", 1)[-1] or "image"
        if "." not in path:
            ext = ".jpg" if self.mime_type == "image/jpeg" else ".png" if self.mime_type == "image/png" else ".webp"
            path += ext
        return path[:120]


@dataclass(slots=True)
class PreparedArticleMedia:
    featured: PreparedMedia | None
    body: list[PreparedMedia]
    video_preview: PreparedMedia | None = None

    @property
    def primary_video(self) -> PreparedMedia | None:
        candidates = [
            item for item in self.body
            if item.kind in {"video", "iframe"} and item.relevance_score >= 45
        ]
        return min(candidates, key=lambda item: (item.position, -item.relevance_score), default=None)

    @property
    def video_link(self) -> str:
        item = self.primary_video
        return _canonical_video_link(item.url) if item is not None else ""

    @property
    def telegram_direct_video(self) -> PreparedMedia | None:
        item = self.primary_video
        if item is None or item.kind != "video":
            return None
        path = urlsplit(item.url).path.casefold()
        if path.endswith((".mp4", ".m4v", ".mov", ".webm")):
            return item
        return None

    @property
    def telegram_hero(self) -> PreparedMedia | None:
        # When the article itself is about a trailer/video and we have a safe
        # preview, that preview outranks a generic hero/OG image.
        if self.primary_video is not None and self.video_preview is not None and self.video_preview.data:
            return self.video_preview
        # Prefer an early, strongly relevant image from the real article body.
        # A later recommendation-card image must never win merely because it is larger.
        early = [
            item for item in self.body
            if item.kind == "image" and item.data and item.relevance_score >= 38 and item.position <= 0.45
        ]
        if early:
            return min(early, key=lambda item: (item.position, -item.relevance_score, -(item.width * item.height)))
        if self.featured and self.featured.kind == "image" and self.featured.data and self.featured.relevance_score >= 38:
            return self.featured
        candidates = [
            item for item in self.body
            if item.kind == "image" and item.data and item.relevance_score >= 45
        ]
        return max(candidates, key=lambda item: (item.relevance_score, -item.position), default=None)


_VIDEO_TITLE_WORDS = (
    "trailer", "teaser", "video", "watch", "featurette", "clip", "footage",
    "трейлер", "тизер", "відео", "ролик",
)


def _youtube_id(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    host = (parts.hostname or "").casefold()
    path = parts.path.strip("/")
    candidate = ""
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = path.split("/", 1)[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}:
        if path.startswith("embed/") or path.startswith("shorts/") or path.startswith("live/"):
            candidate = path.split("/", 1)[1].split("/", 1)[0]
        elif path == "watch":
            candidate = (parse_qs(parts.query).get("v") or [""])[0]
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", candidate or "") else ""


def _canonical_video_link(url: str) -> str:
    video_id = _youtube_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = (parts.hostname or "").casefold()
    if host in {"player.vimeo.com", "www.player.vimeo.com"}:
        match = re.search(r"/video/(\d+)", parts.path)
        if match:
            return f"https://vimeo.com/{match.group(1)}"
    return url


def _youtube_preview(item: PreparedMedia) -> PreparedMedia | None:
    video_id = _youtube_id(item.url)
    if not video_id:
        return None
    for idx, url in enumerate((
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    )):
        preview = PreparedMedia(
            index=-100 - idx, kind="image", url=url, caption=item.caption,
            alt=(item.alt or "Video preview")[:500], position=item.position,
            featured=True, context="youtube video preview", classification="photo",
            relevance_score=max(80.0, item.relevance_score),
        )
        resolved = _probe_image(preview)
        if resolved:
            resolved.relevance_score = max(80.0, item.relevance_score)
            return resolved
    return None


def _image_dimensions(data: bytes, mime: str) -> tuple[int, int]:
    try:
        if mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            return struct.unpack(">II", data[16:24])
        if mime == "image/gif" and data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
            return struct.unpack("<HH", data[6:10])
        if mime == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP" and data[12:16] == b"VP8X" and len(data) >= 30:
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if mime == "image/jpeg" and data[:2] == b"\xff\xd8":
            pos = 2
            while pos + 9 < len(data):
                if data[pos] != 0xFF:
                    pos += 1
                    continue
                marker = data[pos + 1]
                pos += 2
                if marker in {0xD8, 0xD9}:
                    continue
                if pos + 2 > len(data):
                    break
                length = int.from_bytes(data[pos:pos + 2], "big")
                if length < 2 or pos + length > len(data):
                    break
                if marker in {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF} and length >= 7:
                    return int.from_bytes(data[pos + 5:pos + 7], "big"), int.from_bytes(data[pos + 3:pos + 5], "big")
                pos += length
    except Exception:
        return 0, 0
    return 0, 0


def _media_identity(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.casefold()
    path = parts.path.casefold()
    path = re.sub(r"-(?:\d{2,5})x(?:\d{2,5})(?=\.[a-z0-9]{2,5}$)", "", path)
    path = re.sub(r"[_-](?:w|width)[_-]?\d{2,5}(?=\.[a-z0-9]{2,5}$)", "", path)
    return urlunsplit((parts.scheme.casefold(), (parts.hostname or "").casefold(), path, "", ""))


def _text_tokens(value: str) -> set[str]:
    words = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9]{3,}", unquote(str(value or "")).casefold())
    return {word for word in words if word not in {x.casefold() for x in _STOP}}


def _candidate_text(item: PreparedMedia) -> str:
    path = unquote(urlsplit(item.url).path.rsplit("/", 1)[-1])
    return " ".join((item.caption, item.alt, item.context, path))


def _semantic_media_evidence(item: PreparedMedia, *, title: str, article_text: str) -> tuple[int, int, int]:
    """Return (title_overlap, article_overlap, candidate_token_count).

    Media must describe the same story, not merely occur near it on the source page.
    Position/size are ranking signals only; they are never semantic evidence.
    """
    candidate = _text_tokens(_candidate_text(item))
    title_tokens = _text_tokens(title)
    # The opening part of an article carries the event anchors and avoids giving
    # recommendation/footer vocabulary undue influence.
    article_tokens = _text_tokens((title or "") + " " + (article_text or "")[:4500])
    return len(candidate & title_tokens), len(candidate & article_tokens), len(candidate)


def _semantic_media_match(item: PreparedMedia, *, title: str, article_text: str) -> bool:
    """Conservative publication gate for editorial media.

    For body media require actual lexical evidence that the caption/alt/context/file
    belongs to this story.  A metadata-empty featured/OG image is kept as a last-resort source hint,
    but a featured image whose metadata explicitly points elsewhere is rejected.
    """
    title_overlap, article_overlap, token_count = _semantic_media_evidence(
        item, title=title, article_text=article_text
    )
    if item.featured:
        if token_count == 0:
            return True
        return title_overlap >= 1 or article_overlap >= 2
    if item.classification in {"infographic", "screenshot", "map"}:
        return title_overlap >= 1 or article_overlap >= 1
    return title_overlap >= 1 or article_overlap >= 2


def _hard_reject(item: PreparedMedia) -> bool:
    low = (item.url + " " + _candidate_text(item)).casefold().replace("_", "-")
    if any(term in low for term in _HARD_REJECT):
        return True
    if any(term in low for term in _LOGO_WORDS):
        return True
    return False


def _classify(item: PreparedMedia) -> str:
    low = _candidate_text(item).casefold()
    if item.kind in {"video", "iframe"}:
        return "video"
    if any(x in low for x in ("screenshot", "screen shot", "скриншот")):
        return "screenshot"
    if any(x in low for x in ("chart", "graph", "infographic", "diagram", "графік", "діаграм")):
        return "infographic"
    if any(x in low for x in ("map", "карта", "мапа")):
        return "map"
    return "photo" if item.kind == "image" else item.kind


def _score(item: PreparedMedia, *, title: str, article_text: str) -> float:
    if _hard_reject(item):
        return -100.0
    # A large image is not automatically relevant. The old score started every
    # body image at the acceptance threshold, so unrelated recommendation cards
    # passed on size alone. Start lower and require article-position or semantic evidence.
    if item.kind in {"video", "iframe"}:
        score = 42.0 if item.featured else 38.0
        if item.position <= 0.20:
            score += 10.0
        title_low = (title or "").casefold()
        if any(word in title_low for word in _VIDEO_TITLE_WORDS):
            score += 24.0
    else:
        score = 10.0 if item.featured else 16.0
    if item.caption:
        score += 10.0
    if item.alt:
        score += 5.0
    if item.context and not item.featured:
        score += 2.0
    if not item.featured:
        if item.position <= 0.15:
            score += 12.0
        elif item.position <= 0.35:
            score += 7.0
        elif item.position >= 0.70:
            score -= 5.0
    reference = _text_tokens((title or "") + " " + (article_text or "")[:5000])
    title_tokens = _text_tokens(title)
    candidate = _text_tokens(_candidate_text(item))
    title_overlap = len(candidate & title_tokens)
    body_overlap = len(candidate & reference)
    score += min(28.0, title_overlap * 8.0)
    score += min(14.0, max(0, body_overlap - title_overlap) * 2.0)
    if item.width and item.height:
        area = item.width * item.height
        if item.width >= 800 and item.height >= 400:
            score += 5.0
        if area >= 1_000_000:
            score += 2.0
        ratio = item.width / max(1, item.height)
        if ratio > 3.2 or ratio < 0.35:
            score -= 12.0
    if item.classification in {"infographic", "screenshot", "map"} and candidate & reference:
        score += 5.0
    return score


def _probe_image(item: PreparedMedia) -> PreparedMedia | None:
    if _hard_reject(item):
        return None
    try:
        response = fetch_url(item.url, headers=_MEDIA_HEADERS, max_bytes=12 * 1024 * 1024, timeout=20, max_redirects=5, allow_http_errors=True)
    except NetworkError:
        return None
    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    if response.status >= 400 or not mime.startswith("image/") or not response.body:
        return None
    width, height = _image_dimensions(response.body, mime)
    if width and height:
        if width < 300 or height < 180:
            return None
        if width / max(height, 1) >= 4.0:
            return None
    elif len(response.body) < 12_000:
        return None
    item.mime_type = mime
    item.width, item.height = width, height
    item.digest = hashlib.sha256(response.body).hexdigest()
    item.data = response.body
    return item


def _layout_items(layout_json: str, fallback_urls: list[str]) -> tuple[PreparedMedia | None, list[PreparedMedia]]:
    featured: PreparedMedia | None = None
    body: list[PreparedMedia] = []
    try:
        layout = json.loads(layout_json or "{}")
    except Exception:
        layout = {}
    if isinstance(layout, dict):
        featured_raw = str(layout.get("featured") or "").strip()
        featured_video_raw = str(layout.get("featured_video") or "").strip()
        featured_meta = layout.get("featured_meta") if isinstance(layout.get("featured_meta"), dict) else {}
        if featured_raw:
            parsed = valid_public_media(featured_raw)
            if parsed:
                kind, url = parsed
                featured = PreparedMedia(0, kind, url, alt=str(featured_meta.get("alt") or "")[:500], featured=True)
        if featured_video_raw:
            parsed_video = valid_public_media(featured_video_raw)
            if parsed_video:
                video_kind, video_url = parsed_video
                body.append(PreparedMedia(0, video_kind, video_url, position=0.0, featured=True, context="featured video"))
        blocks = layout.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "media":
                    continue
                try:
                    index = int(block.get("index") or len(body) + 1)
                    position = float(block.get("position") or 0.0)
                    width = int(block.get("width") or 0)
                    height = int(block.get("height") or 0)
                except (TypeError, ValueError):
                    index, position, width, height = len(body) + 1, 0.0, 0, 0
                kind = str(block.get("kind") or "image")
                raw_url = str(block.get("url") or "").strip()
                parsed = valid_public_media(raw_url if kind == "image" else f"{kind}|{raw_url}")
                if not parsed:
                    continue
                kind, url = parsed
                body.append(PreparedMedia(
                    index=index, kind=kind, url=url, caption=str(block.get("caption") or "")[:1000],
                    alt=str(block.get("alt") or "")[:500], context=str(block.get("context") or "")[:800],
                    position=max(0.0, min(1.0, position)), width=width, height=height,
                ))
    if not body:
        for idx, raw in enumerate(fallback_urls[:12], start=1):
            parsed = valid_public_media(raw)
            if not parsed:
                continue
            kind, url = parsed
            body.append(PreparedMedia(idx, kind, url, position=min(0.95, 0.75 + idx * 0.03)))
    return featured, body


def prepare_article_media(layout_json: str, fallback_urls: list[str], *, title: str = "", article_text: str = "") -> PreparedArticleMedia:
    """Validate and rank source media. No image is better than an irrelevant banner/logo."""
    featured, body = _layout_items(layout_json, fallback_urls)
    if featured and featured.kind == "image":
        featured.classification = _classify(featured)
        featured = _probe_image(featured)
        if featured:
            featured.relevance_score = _score(featured, title=title, article_text=article_text)
            if featured.relevance_score < 35 or not _semantic_media_match(featured, title=title, article_text=article_text):
                featured = None

    prepared: list[PreparedMedia] = []
    seen_hashes: set[str] = set()
    seen_urls: set[str] = set()
    seen_identities: set[str] = set()
    for item in body:
        identity = _media_identity(item.url)
        if identity in seen_identities or _hard_reject(item):
            continue
        item.classification = _classify(item)
        if item.kind == "image":
            resolved = _probe_image(item)
            if not resolved:
                continue
            if resolved.digest and resolved.digest in seen_hashes:
                continue
            if resolved.url in seen_urls:
                continue
            resolved.relevance_score = _score(resolved, title=title, article_text=article_text)
            # Position and resolution can rank a relevant image, but can never
            # make an unrelated one relevant. This deliberately prefers no photo
            # over a visually plausible recommendation-card/stock image.
            if not _semantic_media_match(resolved, title=title, article_text=article_text):
                continue
            if resolved.relevance_score < 38:
                continue
            if resolved.digest:
                seen_hashes.add(resolved.digest)
            seen_urls.add(resolved.url)
            prepared.append(resolved)
        else:
            item.relevance_score = _score(item, title=title, article_text=article_text)
            video_story = item.kind in {"video", "iframe"} and any(
                word in (title or "").casefold() for word in _VIDEO_TITLE_WORDS
            )
            if not video_story and not _semantic_media_match(item, title=title, article_text=article_text):
                continue
            if item.relevance_score < 38:
                continue
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            prepared.append(item)
        seen_identities.add(identity)
        if len(prepared) >= 3:
            break
    prepared.sort(key=lambda item: (item.position, -item.relevance_score))
    result = PreparedArticleMedia(featured, prepared)
    primary_video = result.primary_video
    if primary_video is not None and primary_video.kind == "iframe":
        result.video_preview = _youtube_preview(primary_video)
    return result
