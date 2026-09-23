from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .media import encode_media


@dataclass(slots=True)
class ExtractedArticle:
    title: str
    text: str
    media_urls: list[str]
    layout_json: str = ""


_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
}
_ALWAYS_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "form", "aside"}
_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"}

_NOISE_PHRASES = (
    "cocoon ai summary", "ai-summary", "ai_summary", "ai summary", "advertorial",
    "sponsored", "sponsor", "affiliate", "newsletter", "related-content",
    "related_content", "recommended-content", "recommended_content", "recommendation-widget", "outbrain",
    "taboola", "revcontent", "ad-slot", "ad_slot", "ad-unit", "ad_unit", "ad-container", "ad_container",
    "google-ad", "google_ad", "doubleclick", "native-ad", "native_ad", "commercial-widget",
)
_NOISE_EXACT_TOKENS = {
    "ad", "ads", "advert", "banner", "banners", "sponsor", "sponsored",
    "affiliate", "recommendations",
}
_MEDIA_CONTEXT_NOISE = {
    "author", "authors", "byline", "avatar", "profile", "headshot", "share", "sharing", "social", "toolbar",
    "newsletter", "subscribe", "subscription", "comment", "comments", "related", "recommended", "recommendations",
}
_BAD_MEDIA_URL_PHRASES = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "amazon-adsystem.com", "adservice.google",
    "outbrain.com", "taboola.com", "/sponsored/", "/sponsor/",
    "/affiliate/", "/banner/", "/banners/", "adserver", "ad-server", "adunit",
    "ad-unit", "tracking", "pixel.gif", "1x1.gif",
)
_BAD_GENERIC_MEDIA_PHRASES = (
    "logo", "avatar", "icon", "sprite", "emoji", "tracking", "pixel", "badge", "favicon", "analytics",
    "cocoon-ai", "cocoon_ai", "cocoon ai", "ai-summary", "ai_summary", "ai summary",
)
_BOILERPLATE_LINES = (
    "cocoon ai summary", "ai-generated summary", "ai generated summary", "powered by cocoon",
    "stay up to date with the latest content by subscribing", "you’re reading electrek", "you're reading electrek",
)


def _normalized_tokens(value: str) -> tuple[str, set[str]]:
    lowered = (value or "").casefold().replace("_", "-")
    plain = re.sub(r"[^a-z0-9]+", " ", lowered)
    return lowered, {token for token in plain.split() if token}


def _looks_noisy_context(value: str) -> bool:
    lowered, tokens = _normalized_tokens(value)
    return any(phrase in lowered for phrase in _NOISE_PHRASES) or bool(tokens & _NOISE_EXACT_TOKENS)


def _looks_noneditorial_media_context(value: str) -> bool:
    lowered, tokens = _normalized_tokens(value)
    if _looks_noisy_context(value):
        return True
    return bool(tokens & _MEDIA_CONTEXT_NOISE)


def _media_url_allowed(url: str) -> bool:
    lowered = url.casefold()
    return not any(token in lowered for token in (*_BAD_GENERIC_MEDIA_PHRASES, *_BAD_MEDIA_URL_PHRASES))


def _best_srcset(value: str) -> str:
    choices: list[tuple[float, str]] = []
    for part in (value or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        score = 1.0
        if len(bits) > 1:
            descriptor = bits[-1].casefold()
            try:
                if descriptor.endswith("w"):
                    score = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    score = float(descriptor[:-1]) * 1000
            except ValueError:
                pass
        choices.append((score, bits[0]))
    return max(choices, default=(0.0, ""), key=lambda item: item[0])[1]


def editorial_media_candidate(
    base_url: str,
    value: str,
    *,
    alt: str = "",
    context: str = "",
    width: int = 0,
    height: int = 0,
    featured: bool = False,
) -> str:
    raw = (value or "").strip()
    if not raw or raw.startswith(("data:", "blob:")):
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    url = urljoin(base_url, raw)
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.hostname or not _media_url_allowed(url):
        return ""
    # Featured metadata is not trusted. Publishers frequently put sponsor banners or
    # AI-summary promos into og:image, so the same hard editorial filters apply.
    if _looks_noneditorial_media_context(" ".join((alt, context))):
        return ""
    if (width and width < 220) or (height and height < 140):
        return ""
    if width >= 360 and height >= 40 and width / max(height, 1) >= 4.0:
        return ""
    return url[:3000]


def _clean_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if len(line) >= 2]
    if not lines:
        return ""
    drop: set[int] = set()
    for idx, line in enumerate(lines):
        low = line.casefold()
        if any(marker in low for marker in _BOILERPLATE_LINES):
            drop.add(idx)
            if "cocoon ai summary" in low:
                if idx > 0 and len(lines[idx - 1]) <= 1400:
                    drop.add(idx - 1)
                if idx + 1 < len(lines) and len(lines[idx + 1]) <= 1400:
                    drop.add(idx + 1)
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


class _ArticleHTMLParser(HTMLParser):
    """Extract article text and preserve editorial media in source order.

    RC6 collected a flat media bag and the old renderer mixed it into article content.
    RC7 records media as blocks at their actual article position. Featured metadata is
    kept separately for the Telegram hero and is not blindly duplicated in the article body.
    """

    def __init__(self, base_url: str, *, include_main: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.include_main = include_main
        self.article_seen = False
        self.main_seen = False
        self.depth = 0
        self.skip_depths: list[int] = []
        self.article_depths: list[int] = []
        self.context_by_depth: dict[int, str] = {}
        self.all_chunks: list[str] = []
        self.title_chunks: list[str] = []
        self.in_title = False
        self.blocks: list[dict[str, object]] = []
        self.text_capture: tuple[int, str, list[str]] | None = None
        self.figure: dict[str, object] | None = None
        self.figcaption_depth = 0
        self.featured_media = ""
        self.featured_alt = ""
        self.featured_title = ""
        self.featured_url = ""
        self.featured_type = ""
        self.twitter_card = ""
        self.featured_video = ""
        self.featured_video_poster = ""

    @property
    def in_article(self) -> bool:
        return bool(self.article_depths)

    @property
    def skipping(self) -> bool:
        return bool(self.skip_depths)

    @staticmethod
    def _attrs_text(values: dict[str, str]) -> str:
        keys = (
            "id", "class", "role", "aria-label", "title", "alt", "rel", "href", "data-testid",
            "data-component", "data-type", "data-name", "data-slot", "data-ad", "data-advertiser", "data-zone",
        )
        return " ".join(values.get(key, "") for key in keys if values.get(key))

    def _context(self, own: str = "") -> str:
        parts = [self.context_by_depth[key] for key in sorted(self.context_by_depth) if self.context_by_depth[key]]
        if own:
            parts.append(own)
        return " ".join(parts)

    @staticmethod
    def _int_attr(value: str) -> int:
        try:
            return int(float(value or "0"))
        except ValueError:
            return 0

    def _image_candidate(self, values: dict[str, str], *, featured: bool = False) -> dict[str, object] | None:
        candidate = (
            values.get("data-src") or values.get("data-lazy-src") or values.get("data-original")
            or values.get("data-original-src") or values.get("data-image-src") or values.get("data-image")
            or _best_srcset(values.get("data-srcset", "")) or _best_srcset(values.get("data-lazy-srcset", ""))
            or _best_srcset(values.get("srcset", "")) or values.get("src") or ""
        )
        alt = values.get("alt", "")
        context = self._context(self._attrs_text(values))
        width, height = self._int_attr(values.get("width", "")), self._int_attr(values.get("height", ""))
        url = editorial_media_candidate(
            self.base_url, candidate, alt=alt, context=context, width=width, height=height, featured=featured,
        )
        if not url:
            return None
        return {
            "kind": "image", "url": url, "alt": " ".join(alt.split())[:500],
            "width": width, "height": height, "context": " ".join(context.split())[:800],
        }

    def _finish_text_capture(self) -> None:
        if not self.text_capture:
            return
        _depth, _tag, chunks = self.text_capture
        text = " ".join("".join(chunks).split()).strip()
        self.text_capture = None
        if len(text) >= 2 and not any(marker in text.casefold() for marker in _BOILERPLATE_LINES):
            if not self.blocks or self.blocks[-1].get("type") != "text" or self.blocks[-1].get("text") != text:
                self.blocks.append({"type": "text", "text": text[:12_000]})

    def _finish_figure(self) -> None:
        if not self.figure:
            return
        candidates = list(self.figure.get("candidates") or [])
        caption = " ".join("".join(self.figure.get("caption_chunks") or []).split()).strip()[:1000]
        if candidates:
            # Choose the largest declared rendition inside a figure. srcset variants
            # and lazy placeholders are therefore collapsed before publication.
            candidates.sort(key=lambda row: (int(row.get("width") or 0) * int(row.get("height") or 0), int(row.get("width") or 0)), reverse=True)
            media = dict(candidates[0])
            media.update({"type": "media", "caption": caption})
            self.blocks.append(media)
        self.figure = None
        self.figcaption_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        self.depth += 1
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        own_context = self._attrs_text(values)
        self.context_by_depth[self.depth] = own_context

        should_skip = tag in _ALWAYS_SKIP_TAGS or _looks_noisy_context(self._context())
        if should_skip and not self.skipping:
            self.skip_depths.append(self.depth)

        if tag == "article" and not self.skipping:
            self.article_seen = True
            self.article_depths.append(self.depth)
        elif tag == "main" and self.include_main and not self.skipping:
            self.main_seen = True
            self.article_depths.append(self.depth)
        if tag == "title":
            self.in_title = True

        if tag == "meta":
            prop = (values.get("property") or values.get("name") or "").casefold()
            content = values.get("content", "").strip()
            if prop in {"og:title", "twitter:title"} and content and not self.featured_title:
                self.featured_title = " ".join(content.split())[:500]
            elif prop == "og:url" and content and not self.featured_url:
                self.featured_url = urljoin(self.base_url, content)[:3000]
            elif prop == "og:type" and content and not self.featured_type:
                self.featured_type = content.casefold()[:120]
            elif prop == "twitter:card" and content and not self.twitter_card:
                self.twitter_card = content.casefold()[:120]
            if prop in {"og:image:alt", "twitter:image:alt"}:
                alt = " ".join(content.split()).strip()
                if alt and not self.featured_alt:
                    self.featured_alt = alt[:500]
            if prop in {"og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"} and not self.featured_media:
                url = editorial_media_candidate(self.base_url, content, alt=self.featured_alt, featured=True)
                if url:
                    self.featured_media = encode_media("image", url)
            if prop in {"og:video:thumbnail_url", "og:video:thumbnail", "video:thumbnail_url"} and not self.featured_video_poster:
                url = editorial_media_candidate(self.base_url, content, context="video poster", featured=True)
                if url:
                    self.featured_video_poster = encode_media("image", url)
            if prop in {"og:video", "og:video:url", "og:video:secure_url", "twitter:player"} and not self.featured_video:
                candidate = content
                low = candidate.casefold()
                kind = "iframe" if any(host in low for host in ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com", "player.vimeo.com")) else "video"
                url = editorial_media_candidate(self.base_url, candidate, context="featured video")
                if url:
                    self.featured_video = encode_media(kind, url)

        if self.in_article and not self.skipping:
            if tag == "figure" and self.figure is None:
                self._finish_text_capture()
                self.figure = {"depth": self.depth, "candidates": [], "caption_chunks": []}
            elif tag == "figcaption" and self.figure is not None:
                self.figcaption_depth = self.depth
            elif tag in _BLOCK_TAGS and self.figure is None and self.text_capture is None:
                self.text_capture = (self.depth, tag, [])

            if tag == "img":
                candidate = self._image_candidate(values)
                if candidate:
                    if self.figure is not None:
                        self.figure["candidates"].append(candidate)  # type: ignore[index]
                    else:
                        self._finish_text_capture()
                        self.blocks.append({"type": "media", **candidate, "caption": ""})
            elif tag == "video":
                poster = (values.get("poster") or values.get("data-poster") or values.get("data-poster-src") or "").strip()
                if poster and not self.featured_video_poster:
                    poster_url = editorial_media_candidate(
                        self.base_url, poster,
                        alt=(values.get("title") or values.get("aria-label") or ""),
                        context=self._context("article video poster"), featured=True,
                    )
                    if poster_url:
                        self.featured_video_poster = encode_media("image", poster_url)
                candidate = values.get("src", "")
                url = editorial_media_candidate(self.base_url, candidate, context=self._context())
                if url:
                    self._finish_text_capture()
                    self.blocks.append({
                        "type": "media", "kind": "video", "url": url, "caption": "",
                        "alt": " ".join((values.get("title") or values.get("aria-label") or "").split())[:500],
                        "context": " ".join(self._context(self._attrs_text(values)).split())[:800],
                    })
            elif tag == "source":
                candidate = values.get("src", "")
                url = editorial_media_candidate(self.base_url, candidate, context=self._context())
                if url:
                    self._finish_text_capture()
                    self.blocks.append({
                        "type": "media", "kind": "video", "url": url, "caption": "",
                        "alt": " ".join((values.get("title") or values.get("aria-label") or "").split())[:500],
                        "context": " ".join(self._context(self._attrs_text(values)).split())[:800],
                    })
            elif tag == "iframe":
                candidate = values.get("src") or values.get("data-src") or values.get("data-lazy-src") or ""
                low = candidate.casefold()
                if any(host in low for host in ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com", "player.vimeo.com")):
                    url = editorial_media_candidate(self.base_url, candidate, context=self._context())
                    if url:
                        self._finish_text_capture()
                        self.blocks.append({
                            "type": "media", "kind": "iframe", "url": url, "caption": "",
                            "alt": " ".join((values.get("title") or values.get("aria-label") or "").split())[:500],
                            "context": " ".join(self._context(self._attrs_text(values)).split())[:800],
                        })
            elif "youtube" in tag or "youtube" in (values.get("class") or "").casefold():
                video_id = values.get("videoid") or values.get("video-id") or values.get("data-videoid") or values.get("data-video-id") or ""
                if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
                    url = editorial_media_candidate(
                        self.base_url, f"https://www.youtube.com/embed/{video_id}", context=self._context(self._attrs_text(values))
                    )
                    if url:
                        self._finish_text_capture()
                        self.blocks.append({
                            "type": "media", "kind": "iframe", "url": url, "caption": "",
                            "alt": " ".join((values.get("title") or values.get("aria-label") or "YouTube video").split())[:500],
                            "context": " ".join(self._context(self._attrs_text(values)).split())[:800],
                        })
            elif tag == "a":
                candidate = values.get("href", "")
                low = candidate.casefold()
                if any(host in low for host in ("youtube.com/watch", "youtu.be/", "vimeo.com/")):
                    url = editorial_media_candidate(self.base_url, candidate, context=self._context(self._attrs_text(values)))
                    if url:
                        self._finish_text_capture()
                        self.blocks.append({
                            "type": "media", "kind": "iframe", "url": url, "caption": "",
                            "alt": " ".join((values.get("title") or values.get("aria-label") or "Video").split())[:500],
                            "context": " ".join(self._context(self._attrs_text(values)).split())[:800],
                        })

        if tag in _VOID_TAGS:
            self.context_by_depth.pop(self.depth, None)
            if self.skip_depths and self.skip_depths[-1] == self.depth:
                self.skip_depths.pop()
            self.depth = max(0, self.depth - 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self.text_capture and self.text_capture[0] == self.depth and tag == self.text_capture[1]:
            self._finish_text_capture()
        if self.figure and int(self.figure.get("depth") or 0) == self.depth and tag == "figure":
            self._finish_figure()
        if tag == "figcaption" and self.figcaption_depth == self.depth:
            self.figcaption_depth = 0
        if tag == "title":
            self.in_title = False
        if self.article_depths and self.article_depths[-1] == self.depth and (tag == "article" or (self.include_main and tag == "main")):
            self._finish_text_capture()
            self.article_depths.pop()
        if self.skip_depths and self.skip_depths[-1] == self.depth:
            self.skip_depths.pop()
        self.context_by_depth.pop(self.depth, None)
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.skipping:
            return
        text = data
        stripped = " ".join(text.split())
        if not stripped:
            return
        if self.in_title:
            self.title_chunks.append(stripped)
        self.all_chunks.append(stripped + " ")
        if self.figure is not None and self.figcaption_depth:
            self.figure["caption_chunks"].append(stripped + " ")  # type: ignore[index]
        elif self.text_capture is not None:
            self.text_capture[2].append(text)


def _normalize_layout(blocks: list[dict[str, object]], featured: str, featured_video: str = "") -> tuple[list[dict[str, object]], list[str]]:
    normalized: list[dict[str, object]] = []
    media_urls: list[str] = []
    seen_url: set[str] = set()
    marker = 0
    text_count = sum(1 for block in blocks if block.get("type") == "text") or 1
    text_seen = 0

    for block in blocks:
        if block.get("type") == "text":
            text = " ".join(str(block.get("text") or "").split()).strip()
            if text:
                normalized.append({"type": "text", "text": text[:12_000]})
                text_seen += 1
            continue
        if block.get("type") != "media":
            continue
        kind = str(block.get("kind") or "image")
        url = str(block.get("url") or "").strip()
        encoded = encode_media(kind, url)
        if not url or encoded in seen_url:
            continue
        seen_url.add(encoded)
        marker += 1
        normalized.append({
            "type": "media",
            "index": marker,
            "kind": kind,
            "url": url,
            "caption": " ".join(str(block.get("caption") or "").split())[:1000],
            "alt": " ".join(str(block.get("alt") or "").split())[:500],
            "position": round(text_seen / text_count, 4),
            "width": int(block.get("width") or 0),
            "height": int(block.get("height") or 0),
            "context": " ".join(str(block.get("context") or "").split())[:800],
        })
        media_urls.append(encoded)
        if marker >= 16:
            break

    if featured and featured not in media_urls:
        media_urls.insert(0, featured)
    if featured_video and featured_video not in media_urls:
        media_urls.insert(0, featured_video)
    layout = {"version": 5, "featured": featured, "featured_video": featured_video, "blocks": normalized}
    return normalized, media_urls[:24]



_JSONLD_SCRIPT_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S,
)



_ARTICLE_TYPES = {"article", "newsarticle", "blogposting", "report", "analysisnewsarticle"}
_GENERIC_TITLE_TOKENS = {
    "this", "that", "with", "from", "into", "about", "after", "before", "their", "your", "they", "have", "will",
    "news", "story", "article", "image", "photo", "video", "brand", "campaign", "company",
}


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9\u0400-\u04ff]+", (value or "").casefold())
        if len(token) >= 4 and token not in _GENERIC_TITLE_TOKENS
    }


def _same_article_url(left: str, right: str) -> bool:
    try:
        a, b = urlsplit(left or ""), urlsplit(right or "")
    except ValueError:
        return False
    if not a.hostname or not b.hostname or a.hostname.casefold() != b.hostname.casefold():
        return False
    pa = re.sub(r"/+", "/", a.path or "/").rstrip("/") or "/"
    pb = re.sub(r"/+", "/", b.path or "/").rstrip("/") or "/"
    return pa == pb


def _metadata_matches_article(meta_title: str, meta_url: str, base_url: str, title: str) -> bool:
    title_tokens = _meaningful_tokens(title)
    meta_tokens = _meaningful_tokens(meta_title)
    title_ok = bool(title_tokens and meta_tokens and (title_tokens & meta_tokens))
    url_ok = bool(meta_url and base_url and _same_article_url(meta_url, base_url))
    return title_ok and url_ok


def _media_url_tokens(value: str) -> set[str]:
    try:
        path = urlsplit(value or "").path
    except ValueError:
        path = value or ""
    return _meaningful_tokens(path.replace("-", " ").replace("_", " "))


def _safe_og_featured(
    featured: str,
    alt: str,
    title: str,
    *,
    meta_title: str = "",
    meta_url: str = "",
    meta_type: str = "",
    base_url: str = "",
) -> str:
    """Use page-level OG/Twitter image only when the asset itself is tied to the story.

    A matching og:title/og:url is necessary context but is not enough by itself: stale
    CMS cards can retain a foreign image while all other page metadata is correct. The
    image needs its own evidence via alt text, URL slug/article id, or equivalent tokens.
    """
    raw = str(featured or "").strip()
    if not raw:
        return ""
    title_tokens = _meaningful_tokens(title)
    if not title_tokens:
        return ""
    alt_tokens = _meaningful_tokens(alt)
    if alt_tokens & title_tokens:
        return raw
    asset_tokens = _media_url_tokens(raw)
    if asset_tokens & title_tokens:
        return raw
    try:
        source_path = urlsplit(base_url or "").path
        image_path = urlsplit(raw).path
    except ValueError:
        source_path = image_path = ""
    source_ids = set(re.findall(r"\d{6,}", source_path))
    image_ids = set(re.findall(r"\d{6,}", image_path))
    page_meta_ok = _metadata_matches_article(meta_title, meta_url, base_url, title)
    type_ok = not meta_type or "article" in meta_type or "website" in meta_type
    if page_meta_ok and type_ok and source_ids and (source_ids & image_ids):
        return raw
    return ""


def _image_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("url", "contentUrl", "thumbnailUrl"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                yield item.strip()
    elif isinstance(value, list):
        for item in value:
            yield from _image_values(item)


def _jsonld_nodes(html: str) -> list[dict]:
    nodes: list[dict] = []
    def walk(node):
        if isinstance(node, dict):
            nodes.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    for raw in _JSONLD_SCRIPT_RE.findall(str(html or "")):
        try:
            payload = json.loads(raw.strip())
        except Exception:
            continue
        walk(payload)
    return nodes


def _node_types(node: dict) -> set[str]:
    raw_type = node.get("@type")
    values = raw_type if isinstance(raw_type, list) else [raw_type]
    return {str(value or "").casefold() for value in values if value}


def _node_url_candidates(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("@id", "url"):
            item = value.get(key)
            if isinstance(item, str):
                yield item
    elif isinstance(value, list):
        for item in value:
            yield from _node_url_candidates(item)


def _jsonld_node_matches_article(node: dict, *, title: str, base_url: str) -> bool:
    article_title = str(node.get("headline") or node.get("name") or "")
    title_tokens = _meaningful_tokens(title)
    node_tokens = _meaningful_tokens(article_title)
    if title_tokens and node_tokens and (title_tokens & node_tokens):
        return True
    for key in ("mainEntityOfPage", "url", "@id"):
        for candidate in _node_url_candidates(node.get(key)):
            if _same_article_url(base_url, urljoin(base_url, candidate)):
                return True
    return False


def _jsonld_article_image_candidate(html: str, base_url: str, title: str = "") -> str:
    """Return a schema.org Article image tied to the current article, not a related card."""
    article_nodes = [node for node in _jsonld_nodes(html) if _node_types(node) & _ARTICLE_TYPES]
    ordered = [node for node in article_nodes if _jsonld_node_matches_article(node, title=title, base_url=base_url)]
    if len(article_nodes) == 1 and article_nodes[0] not in ordered:
        ordered.append(article_nodes[0])
    for node in ordered:
        for key in ("image", "thumbnailUrl", "primaryImageOfPage"):
            for candidate in _image_values(node.get(key)):
                url = editorial_media_candidate(base_url, candidate, context="schema article image", featured=True)
                if url:
                    return encode_media("image", url)
    return ""


def _video_object_values(node: dict, base_url: str) -> tuple[str, str]:
    video = ""
    poster = ""
    for key in ("contentUrl", "embedUrl", "url"):
        value = node.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        absolute = urljoin(base_url, value.strip())
        low = absolute.casefold()
        if any(host in low for host in ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com", "player.vimeo.com")):
            url = editorial_media_candidate(base_url, absolute, context="jsonld video")
            if url:
                video = encode_media("iframe", url)
                break
        path = urlsplit(absolute).path.casefold()
        if path.endswith((".mp4", ".m4v", ".mov", ".webm")):
            url = editorial_media_candidate(base_url, absolute, context="jsonld video")
            if url:
                video = encode_media("video", url)
                break
    for key in ("thumbnailUrl", "thumbnail", "image"):
        for candidate in _image_values(node.get(key)):
            url = editorial_media_candidate(base_url, candidate, context="verified video poster", featured=True)
            if url:
                poster = encode_media("image", url)
                break
        if poster:
            break
    return video, poster


def _jsonld_video_media_candidates(html: str, base_url: str, title: str = "") -> tuple[str, str]:
    """Return (video, poster) only from VideoObject data attributable to this story."""
    nodes = _jsonld_nodes(html)
    # Strongest case: a VideoObject nested directly under the matching Article node.
    articles = [node for node in nodes if _node_types(node) & _ARTICLE_TYPES and _jsonld_node_matches_article(node, title=title, base_url=base_url)]
    for article in articles:
        video_value = article.get("video")
        candidates: list[dict] = []
        def collect(value):
            if isinstance(value, dict):
                if "videoobject" in _node_types(value):
                    candidates.append(value)
                for nested in value.values():
                    collect(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect(nested)
        collect(video_value)
        for candidate in candidates:
            video, poster = _video_object_values(candidate, base_url)
            if video or poster:
                return video, poster
    # Some CMSes expose the VideoObject as a sibling in @graph. Require its own
    # title/name/description to overlap this article before trusting the thumbnail.
    title_tokens = _meaningful_tokens(title)
    for node in nodes:
        if "videoobject" not in _node_types(node):
            continue
        own = " ".join(str(node.get(key) or "") for key in ("name", "headline", "description"))
        if title_tokens and not (title_tokens & _meaningful_tokens(own)):
            continue
        video, poster = _video_object_values(node, base_url)
        if video or poster:
            return video, poster
    return "", ""

def _parse_scope(html: str, base_url: str, *, include_main: bool) -> _ArticleHTMLParser:
    parser = _ArticleHTMLParser(base_url, include_main=include_main)
    parser.feed(html)
    parser.close()
    parser._finish_text_capture()
    parser._finish_figure()
    return parser


def extract_article_content(html: str, base_url: str = "") -> ExtractedArticle:
    # Prefer the semantic <article> element.  Crucially, body media is extracted
    # independently from page-level OG metadata.  RC70 could publish a stale/unrelated
    # OG image when a publisher page exposed no body image, which is worse than no media.
    article_parser = _parse_scope(html, base_url, include_main=False)
    article_blocks, article_media = _normalize_layout(article_parser.blocks, "", article_parser.featured_video)
    article_text = _clean_text("\n".join(
        str(block.get("text") or "") for block in article_blocks if block.get("type") == "text"
    ))

    parser = article_parser
    blocks = article_blocks
    media = article_media
    text = article_text
    if not article_parser.article_seen or len(article_text) < 50:
        main_parser = _parse_scope(html, base_url, include_main=True)
        main_blocks, main_media = _normalize_layout(main_parser.blocks, "", main_parser.featured_video)
        main_text = _clean_text("\n".join(
            str(block.get("text") or "") for block in main_blocks if block.get("type") == "text"
        ))
        if len(main_text) >= max(50, len(article_text)):
            parser, blocks, media, text = main_parser, main_blocks, main_media, main_text

    if not text:
        text = _clean_text("".join(parser.all_chunks))

    title = " ".join(parser.title_chunks or article_parser.title_chunks).strip()

    # Recover JS-rendered publisher video + thumbnail from schema.org VideoObject.
    jsonld_video, jsonld_video_poster = _jsonld_video_media_candidates(html, base_url, title)
    if not parser.featured_video and jsonld_video:
        parser.featured_video = jsonld_video
        if parser.featured_video not in media:
            media.insert(0, parser.featured_video)
    if not parser.featured_video_poster and jsonld_video_poster:
        parser.featured_video_poster = jsonld_video_poster

    # Media trust order:
    #   1. media structurally inside <article>/<main>,
    #   2. schema.org Article.image tied to this article,
    #   3. a poster/thumbnail tied to this article's VideoObject/player,
    #   4. OG/Twitter image only with asset-level evidence that it belongs here.
    # Foreign/stale page cards fail closed instead of becoming Telegram artwork.
    jsonld_featured = _jsonld_article_image_candidate(html, base_url, title)
    selected_featured = ""
    # Iframe embeds are useful evidence/video links but are not uploadable Telegram
    # media. Treat an iframe-only story as still needing a verified image/poster.
    publishable_media = [item for item in media if not str(item).startswith("iframe|")]
    provenance = "body" if publishable_media else "none"
    if not publishable_media and jsonld_featured:
        selected_featured = jsonld_featured
        media.insert(0, jsonld_featured)
        provenance = "jsonld_article_image"
    elif not publishable_media:
        video_poster = parser.featured_video_poster
        if not video_poster and parser.twitter_card == "player" and parser.featured_video and parser.featured_media:
            # Twitter player cards define twitter:image as the player's own poster.
            video_poster = parser.featured_media
        if video_poster:
            selected_featured = video_poster
            media.insert(0, video_poster)
            provenance = "verified_video_poster"
        else:
            selected_featured = _safe_og_featured(
                parser.featured_media, parser.featured_alt, title,
                meta_title=parser.featured_title, meta_url=parser.featured_url,
                meta_type=parser.featured_type, base_url=base_url,
            )
            if selected_featured:
                media.insert(0, selected_featured)
                provenance = "verified_og"
            elif parser.featured_media:
                provenance = "rejected_foreign"

    layout_json = json.dumps({
        "version": 7,
        "featured": selected_featured,
        "featured_video": parser.featured_video,
        "featured_meta": {
            "alt": parser.featured_alt,
            "provenance": provenance,
            "page_title": parser.featured_title,
            "page_url": parser.featured_url,
        },
        "blocks": blocks,
    }, ensure_ascii=False, separators=(",", ":"))
    return ExtractedArticle(title[:500], text[:120_000], list(dict.fromkeys(media))[:24], layout_json)


def extract_article(html: str) -> tuple[str, str]:
    result = extract_article_content(html)
    return result.title, result.text
