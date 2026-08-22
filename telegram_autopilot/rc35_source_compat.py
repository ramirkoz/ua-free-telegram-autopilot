from __future__ import annotations

from urllib.parse import urlsplit

_ACCESS_HTTP_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 429")
_INSTALLED = False


def is_access_http_error(error: BaseException | str) -> bool:
    text = str(error)
    return any(marker in text for marker in _ACCESS_HTTP_MARKERS)


def source_feed_candidates(url: str) -> list[str]:
    """Return conservative RSS/Atom candidates for a public editorial page.

    Path-specific candidates come before site-wide feeds. Reuters gets explicit
    legacy/public feed aliases because its public section pages can answer 401 to
    non-browser clients even when the feed endpoint remains readable.
    """
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return []
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return []

    host = parts.hostname.casefold().rstrip(".")
    bare_host = host.removeprefix("www.")
    path = parts.path or "/"
    path_low = path.casefold().rstrip("/") or "/"
    origin = f"{parts.scheme}://{host}"
    candidates: list[str] = []

    def add(value: str) -> None:
        if value and value not in candidates:
            candidates.append(value)

    if bare_host == "reuters.com":
        if path_low in {"/technology", "/news/technology"} or path_low.startswith("/technology/"):
            for value in (
                "https://feeds.reuters.com/reuters/technologyNews?format=xml",
                "https://feeds.reuters.com/reuters/technologyNews",
                "http://feeds.reuters.com/reuters/technologyNews?format=xml",
                "http://feeds.reuters.com/reuters/technologyNews",
            ):
                add(value)
        elif path_low.startswith("/science"):
            for value in (
                "https://feeds.reuters.com/reuters/scienceNews?format=xml",
                "https://feeds.reuters.com/reuters/scienceNews",
                "http://feeds.reuters.com/reuters/scienceNews?format=xml",
            ):
                add(value)
        elif path_low.startswith("/business") or path_low.startswith("/markets"):
            for value in (
                "https://feeds.reuters.com/reuters/businessNews?format=xml",
                "https://feeds.reuters.com/reuters/businessNews",
                "http://feeds.reuters.com/reuters/businessNews?format=xml",
            ):
                add(value)

    base_path = path.rstrip("/")
    if base_path:
        for suffix in ("/feed/", "/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml"):
            add(origin + base_path + suffix)
    for suffix in ("/feed/", "/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml"):
        add(origin + suffix)
    return candidates


def install_rc35_source_compat() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import collector as collector_module
    from . import service as service_module
    from . import ui as ui_module

    original_detect_source = collector_module.detect_source
    original_collect_source = collector_module.collect_source
    base_headers = dict(collector_module._SOURCE_REQUEST_HEADERS)

    def source_fetch(url: str, **kwargs):
        supplied = dict(kwargs.pop("headers", {}) or {})
        headers = dict(base_headers)
        headers.update(
            {
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "DNT": "1",
                "Sec-CH-UA": '"Chromium";v="142", "Not_A Brand";v="99"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
            }
        )
        headers.update(supplied)
        try:
            return collector_module.fetch_url(url, headers=headers, **kwargs)
        except collector_module.NetworkError as exc:
            if not is_access_http_error(exc):
                raise
            parts = urlsplit(url)
            retry_headers = dict(headers)
            if parts.scheme in {"http", "https"} and parts.hostname:
                retry_headers.update(
                    {
                        "Referer": f"{parts.scheme}://{parts.hostname}/",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-User": "?1",
                    }
                )
            return collector_module.fetch_url(url, headers=retry_headers, **kwargs)

    def try_feed(page_url: str):
        for candidate in source_feed_candidates(page_url):
            try:
                response = source_fetch(candidate, max_bytes=8 * 1024 * 1024, timeout=22)
                items = collector_module.parse_rss(response.body)
                if items:
                    return collector_module.SourceDetection(
                        "rss",
                        response.final_url,
                        collector_module._suggested_name(page_url, "rss"),
                    )
            except Exception:
                continue
        return None

    def detect_source(value: str):
        normalized = collector_module.normalize_source_url(value)
        username = collector_module._telegram_username(normalized)
        if username:
            return collector_module.SourceDetection("telegram", f"https://t.me/{username}", "@" + username)

        # Known difficult publishers are checked through their public feed aliases
        # before touching a section page that may answer 401/403 to automation.
        parts = urlsplit(normalized)
        if (parts.hostname or "").casefold().removeprefix("www.") == "reuters.com":
            feed = try_feed(normalized)
            if feed is not None:
                return feed
        try:
            return original_detect_source(normalized)
        except Exception as exc:
            if not is_access_http_error(exc):
                raise
            feed = try_feed(normalized)
            if feed is not None:
                return feed
            # A public page blocked only during detection may still become readable
            # later or through a generic feed fallback. Do not make the Add Source
            # dialog itself unusable just because a CDN dislikes this one probe.
            return collector_module.SourceDetection(
                "page", normalized, collector_module._suggested_name(normalized, "page")
            )

    def common_feed_candidates(url: str) -> list[str]:
        return source_feed_candidates(url)

    def collect_source(source):
        try:
            return original_collect_source(source)
        except collector_module.CollectorError as exc:
            if source.kind != "page" or not is_access_http_error(exc):
                raise
            fallback = collector_module._collect_common_feed_fallback(source)
            if fallback:
                return fallback
            raise collector_module.CollectorError(
                "Сайт блокує автоматичне читання (HTTP 401/403/429), і придатний RSS/Atom fallback не знайдено."
            ) from exc

    collector_module._source_fetch = source_fetch
    collector_module._common_feed_candidates = common_feed_candidates
    collector_module.detect_source = detect_source
    collector_module.collect_source = collect_source

    # ui.py and service.py imported these functions by value, so update their
    # module-level aliases as well. RC33's source dialog calls ui.detect_source.
    ui_module.detect_source = detect_source
    service_module.collect_source = collect_source

    _INSTALLED = True
