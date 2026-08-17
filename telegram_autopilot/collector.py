from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .article_extractor import editorial_media_candidate, extract_article_content
from .models import CollectedArticle, Source
from .media import encode_media
from .network import NetworkError, fetch_url


class CollectorError(RuntimeError):
    pass

_SOURCE_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
        "text/xml;q=0.9, text/html;q=0.8, application/xhtml+xml;q=0.8, */*;q=0.5"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _source_fetch(url: str, **kwargs):
    """Fetch a public editorial source with normal browser-like request headers.

    A number of otherwise public RSS/news endpoints reject bare library user
    agents with HTTP 403. Keep this behavior scoped to source collection so API
    calls to Telegram, Telegraph and AI providers retain their own headers.
    """
    supplied = dict(kwargs.pop("headers", {}) or {})
    headers = dict(_SOURCE_REQUEST_HEADERS)
    headers.update(supplied)
    try:
        return fetch_url(url, headers=headers, **kwargs)
    except NetworkError as exc:
        # Some CDNs are stricter on the first anonymous request. A second normal
        # document-navigation profile is harmless for public GET sources and
        # fixes feeds that gate on browser navigation headers.
        if "HTTP 403" not in str(exc):
            raise
        retry_headers = dict(headers)
        parts = urlsplit(url)
        if parts.scheme in {"http", "https"} and parts.hostname:
            retry_headers.update({
                "Referer": f"{parts.scheme}://{parts.hostname}/",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
            })
        return fetch_url(url, headers=retry_headers, **kwargs)


def _network_error_for_source(exc: NetworkError) -> CollectorError:
    text = str(exc)
    if "HTTP 403" in text:
        return CollectorError(
            "Сервер джерела відхилив автоматичний запит (HTTP 403). "
            "Адреса може бути правильною, але сайт блокує автоматичне читання."
        )
    return CollectorError(text)


@dataclass(frozen=True, slots=True)
class SourceDetection:
    kind: str
    url: str
    suggested_name: str


def _telegram_username(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("@"):
        candidate = raw[1:]
    else:
        if "://" not in raw:
            raw = "https://" + raw
        try:
            parts = urlsplit(raw)
        except ValueError:
            return ""
        host = (parts.hostname or "").casefold().rstrip(".")
        if host not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me", "telegram.dog", "www.telegram.dog"}:
            return ""
        segments = [segment for segment in parts.path.split("/") if segment]
        if segments and segments[0].casefold() == "s":
            segments = segments[1:]
        if not segments:
            return ""
        candidate = segments[0]
    candidate = candidate.strip().lstrip("@").rstrip("/")
    if candidate.startswith("+") or candidate.casefold() == "joinchat":
        raise CollectorError("Підтримуються лише публічні Telegram-канали з адресою t.me/username.")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,64}", candidate):
        return ""
    return candidate


def normalize_source_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise CollectorError("Вставте адресу джерела.")
    username = _telegram_username(raw)
    if username:
        return f"https://t.me/{username}"
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise CollectorError("Адреса джерела має неправильний формат.") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise CollectorError("Потрібна HTTP/HTTPS адреса або публічний Telegram-канал.")
    if parts.username or parts.password:
        raise CollectorError("Адреса джерела не повинна містити логін або пароль.")
    host = parts.hostname.lower().rstrip(".")
    netloc = host
    if parts.port and parts.port not in {80, 443}:
        raise CollectorError("Підтримуються лише стандартні HTTP/HTTPS порти.")
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


class _FeedDiscoveryParser(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.feeds: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "link":
            return
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        rel = {token.casefold() for token in values.get("rel", "").split()}
        media_type = values.get("type", "").casefold()
        href = values.get("href", "")
        if "alternate" not in rel or not href:
            return
        if media_type not in {"application/rss+xml", "application/atom+xml", "application/feed+json", "text/xml", "application/xml"}:
            return
        resolved = urljoin(self.base, href)
        if resolved.startswith(("http://", "https://")) and resolved not in self.feeds:
            self.feeds.append(resolved)


def _suggested_name(url: str, kind: str) -> str:
    if kind == "telegram":
        username = _telegram_username(url)
        return "@" + username if username else "Telegram"
    host = (urlsplit(url).hostname or "Джерело").removeprefix("www.")
    return host


def _looks_like_feed(body: bytes, content_type: str) -> bool:
    if content_type in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}:
        return True
    sample = body[:2048].lstrip().lower()
    return sample.startswith(b"<?xml") or b"<rss" in sample or b"<feed" in sample


def detect_source(value: str) -> SourceDetection:
    """Resolve a pasted address into Telegram, RSS/Atom, or a normal web page.

    A normal site that advertises an RSS/Atom feed is automatically upgraded to
    that feed. This keeps setup URL-only and avoids a pointless source-type picker.
    """
    normalized = normalize_source_url(value)
    username = _telegram_username(normalized)
    if username:
        return SourceDetection("telegram", f"https://t.me/{username}", "@" + username)
    try:
        response = _source_fetch(normalized, max_bytes=8 * 1024 * 1024, timeout=35)
    except NetworkError as exc:
        raise _network_error_for_source(exc) from exc
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    if _looks_like_feed(response.body, content_type):
        try:
            items = parse_rss(response.body)
        except CollectorError:
            items = []
        if items:
            return SourceDetection("rss", response.final_url, _suggested_name(response.final_url, "rss"))
    if content_type not in {"text/html", "application/xhtml+xml", ""}:
        raise CollectorError(f"Не вдалося визначити джерело: сервер повернув {content_type}.")
    html = response.body.decode("utf-8", errors="replace")
    feed_parser = _FeedDiscoveryParser(response.final_url)
    feed_parser.feed(html)
    for candidate in feed_parser.feeds[:4]:
        try:
            feed_response = _source_fetch(candidate, max_bytes=8 * 1024 * 1024, timeout=25)
            if parse_rss(feed_response.body):
                return SourceDetection("rss", feed_response.final_url, _suggested_name(response.final_url, "rss"))
        except Exception:
            continue
    return SourceDetection("page", response.final_url, _suggested_name(response.final_url, "page"))


class _TextAndImageParser(HTMLParser):
    def __init__(self, base: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.parts: list[str] = []
        self.images: list[str] = []
        self.video_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag in {"br", "p", "div", "li", "blockquote"}:
            self.parts.append("\n")
        if tag == "img":
            value = values.get("data-src") or values.get("data-lazy-src") or values.get("src") or ""
            try:
                width = int(float(values.get("width") or "0"))
                height = int(float(values.get("height") or "0"))
            except ValueError:
                width = height = 0
            url = editorial_media_candidate(
                self.base, value, alt=values.get("alt", ""),
                context=" ".join((values.get("class", ""), values.get("id", ""), values.get("title", ""))),
                width=width, height=height,
            )
            if url:
                encoded = encode_media("image", url)
                if encoded not in self.images:
                    self.images.append(encoded[:3020])
        elif tag == "video":
            self.video_depth += 1
            value = values.get("src") or ""
            if value:
                url = urljoin(self.base, value)
                encoded = encode_media("video", url)
                if url.startswith(("http://", "https://")) and encoded not in self.images:
                    self.images.append(encoded[:3020])
        elif tag == "source" and self.video_depth:
            value = values.get("src") or ""
            if value:
                url = urljoin(self.base, value)
                encoded = encode_media("video", url)
                if url.startswith(("http://", "https://")) and encoded not in self.images:
                    self.images.append(encoded[:3020])
        elif tag == "iframe":
            value = values.get("src") or ""
            low = value.casefold()
            if value and any(host in low for host in ("youtube.com", "youtu.be", "vimeo.com", "player.vimeo.com")):
                url = urljoin(self.base, value)
                encoded = encode_media("iframe", url)
                if url.startswith(("http://", "https://")) and encoded not in self.images:
                    self.images.append(encoded[:3020])

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "video" and self.video_depth:
            self.video_depth -= 1

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def _strip_html(value: str, base: str = "") -> tuple[str, list[str]]:
    parser = _TextAndImageParser(base)
    parser.feed(value or "")
    return parser.text(), parser.images


def _first_text(element: ET.Element, names: set[str]) -> str:
    for child in element.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text:
            return child.text.strip()
    return ""


def _rss_media(node: ET.Element, base: str) -> list[str]:
    result: list[str] = []
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        attrs = {str(k).rsplit("}", 1)[-1].lower(): str(v) for k, v in child.attrib.items()}
        url = ""
        kind = "image"
        media_type = str(attrs.get("type", "")).casefold()
        if local in {"content", "thumbnail"}:
            url = attrs.get("url", "")
            if media_type.startswith("video/"):
                kind = "video"
        elif local == "enclosure" and (media_type.startswith("image/") or media_type.startswith("video/")):
            url = attrs.get("url", "")
            kind = "video" if media_type.startswith("video/") else "image"
        if url:
            resolved = urljoin(base, url)
            encoded = encode_media(kind, resolved)
            if resolved.startswith(("http://", "https://")) and encoded not in result:
                result.append(encoded[:3020])
    return result


def parse_rss(xml_bytes: bytes) -> list[CollectedArticle]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise CollectorError("RSS/Atom XML має неправильний формат.") from exc
    items: list[CollectedArticle] = []
    candidates = [n for n in root.iter() if n.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    for node in candidates[:60]:
        title = _first_text(node, {"title"})
        link = _first_text(node, {"link"})
        if not link:
            for child in node:
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        guid = _first_text(node, {"guid", "id"}) or link or title
        description = _first_text(node, {"encoded", "content", "description", "summary"})
        published = _first_text(node, {"pubdate", "published", "updated", "date"}) or None
        text, embedded = _strip_html(description, link)
        media: list[str] = []
        for url in _rss_media(node, link) + embedded:
            if url not in media:
                media.append(url)
        if not guid or not (title or text):
            continue
        items.append(CollectedArticle(guid[:1000], title or text[:180] or "Без заголовка", link, text, published, media[:24]))
    return items


def _enrich_article(item: CollectedArticle) -> CollectedArticle:
    if not item.url:
        return item
    try:
        response = _source_fetch(
            item.url,
            max_bytes=6 * 1024 * 1024,
            allowed_content_types={"text/html", "application/xhtml+xml"},
            timeout=25,
        )
        extracted = extract_article_content(response.body.decode("utf-8", errors="replace"), item.url)
        if len(extracted.text) > len(item.raw_text):
            item.raw_text = extracted.text
        if extracted.layout_json:
            item.article_layout_json = extracted.layout_json
        if (not item.title or item.title == "Без заголовка") and extracted.title:
            item.title = extracted.title
        # Once the actual article page is available, trust its structurally filtered
        # editorial media over images embedded in RSS descriptions, which often
        # contain ad creatives or newsletter banners. RSS media remains a fallback
        # only when the article page exposes no usable editorial media.
        preferred_media = extracted.media_urls if extracted.media_urls else item.media_urls
        item.media_urls = list(dict.fromkeys(preferred_media))[:24]
    except Exception:
        pass
    return item


def hydrate_article_page(url: str, title: str = "", raw_text: str = "", media_urls: list[str] | None = None) -> CollectedArticle:
    """Re-fetch an article and attach RC7 structured article layout.

    This makes copied RC6 Data compatible without asking the user to rebuild sources.
    """
    return _enrich_article(CollectedArticle(
        external_id=url or title or "hydrate",
        title=title or "Без заголовка",
        url=url,
        raw_text=raw_text,
        published_at=None,
        media_urls=list(media_urls or []),
    ))


class _LinkParser(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []
        self._depth = 0
        self._a_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        if tag.lower() == "a":
            href = dict(attrs).get("href") or ""
            if href:
                self._href = urljoin(self.base, href)
                self._text = []
                self._a_depth = self._depth

    def handle_data(self, data: str) -> None:
        if self._a_depth is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._a_depth == self._depth and tag.lower() == "a":
            text = " ".join("".join(self._text).split())
            if text and self._href.startswith(("http://", "https://")):
                self.links.append((self._href, text))
            self._href = ""; self._text = []; self._a_depth = None
        self._depth = max(0, self._depth - 1)


class _TelegramChannelParser(HTMLParser):
    def __init__(self, username: str) -> None:
        super().__init__(convert_charrefs=True)
        self.username = username
        self.depth = 0
        self.message_depth: int | None = None
        self.text_depth: int | None = None
        self.current: dict[str, object] | None = None
        self.items: list[CollectedArticle] = []

    @staticmethod
    def _classes(attrs: dict[str, str]) -> set[str]:
        return {item for item in attrs.get("class", "").split() if item}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.depth += 1
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        classes = self._classes(values)
        if tag.casefold() == "div" and "tgme_widget_message" in classes and values.get("data-post"):
            self._finish_current()
            self.current = {"post": values["data-post"], "text": [], "published": None, "media": []}
            self.message_depth = self.depth
        if self.current is None:
            return
        if "tgme_widget_message_text" in classes:
            self.text_depth = self.depth
        if tag.casefold() == "time" and values.get("datetime"):
            self.current["published"] = values["datetime"]
        media = self.current["media"]
        assert isinstance(media, list)
        if tag.casefold() == "img" and values.get("src"):
            encoded = encode_media("image", values["src"])
            if encoded not in media:
                media.append(encoded[:3020])
        if tag.casefold() in {"video", "source"} and values.get("src"):
            encoded = encode_media("video", values["src"])
            if encoded not in media:
                media.append(encoded[:3020])
        style = values.get("style", "")
        if style:
            match = re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)", style, flags=re.I)
            if match:
                url = match.group(1)
                encoded = encode_media("image", url)
                if encoded not in media:
                    media.append(encoded[:3020])

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.text_depth is not None and self.depth >= self.text_depth:
            text = self.current["text"]
            assert isinstance(text, list)
            text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is not None and self.text_depth == self.depth:
            self.text_depth = None
        if self.current is not None and self.message_depth == self.depth and tag.casefold() == "div":
            self._finish_current()
        self.depth = max(0, self.depth - 1)

    def close(self) -> None:
        super().close()
        self._finish_current()

    def _finish_current(self) -> None:
        if not self.current:
            return
        post = str(self.current.get("post") or "").strip()
        text_parts = self.current.get("text")
        text = " ".join("".join(text_parts if isinstance(text_parts, list) else []).split())
        media = self.current.get("media")
        media_list = list(media) if isinstance(media, list) else []
        if post and text:
            url = "https://t.me/" + post
            title = text[:220] + ("…" if len(text) > 220 else "")
            self.items.append(
                CollectedArticle(post[:1000], title, url, text, str(self.current.get("published") or "") or None, media_list[:24])
            )
        self.current = None
        self.message_depth = None
        self.text_depth = None


def _collect_telegram(source: Source) -> list[CollectedArticle]:
    username = _telegram_username(source.url)
    if not username:
        raise CollectorError("Telegram-джерело має містити публічну адресу t.me/username.")
    response = _source_fetch(
        f"https://t.me/s/{username}",
        max_bytes=8 * 1024 * 1024,
        allowed_content_types={"text/html", "application/xhtml+xml"},
        timeout=35,
    )
    parser = _TelegramChannelParser(username)
    parser.feed(response.body.decode("utf-8", errors="replace"))
    parser.close()
    if not parser.items:
        raise CollectorError("Не вдалося прочитати публікації Telegram-каналу. Перевірте, що канал публічний.")
    return parser.items[-40:]


def collect_source(source: Source) -> list[CollectedArticle]:
    try:
        if source.kind == "telegram":
            return _collect_telegram(source)
        if source.kind == "rss":
            response = _source_fetch(
                source.url,
                max_bytes=8 * 1024 * 1024,
                allowed_content_types={"application/rss+xml", "application/atom+xml", "application/xml", "text/xml", "text/plain"},
                timeout=35,
            )
            items = parse_rss(response.body)
            for item in items[:20]:
                _enrich_article(item)
            return items[:40]
        if source.kind == "page":
            response = _source_fetch(
                source.url,
                max_bytes=5 * 1024 * 1024,
                allowed_content_types={"text/html", "application/xhtml+xml"},
                timeout=35,
            )
            html = response.body.decode("utf-8", errors="replace")
            parser = _LinkParser(source.url)
            parser.feed(html)
            base_host = (urlsplit(source.url).hostname or "").lower()
            seen: set[str] = set()
            result: list[CollectedArticle] = []
            for url, text in parser.links:
                host = (urlsplit(url).hostname or "").lower()
                if host != base_host or url in seen or len(text) < 18:
                    continue
                seen.add(url)
                item = _enrich_article(CollectedArticle(hashlib.sha256(url.encode("utf-8")).hexdigest(), text[:500], url, "", None, []))
                if len(item.raw_text) < 250:
                    continue
                result.append(item)
                if len(result) >= 30:
                    break
            return result
    except NetworkError as exc:
        raise _network_error_for_source(exc) from exc
    raise CollectorError(f"Непідтримуваний тип джерела: {source.kind}")
