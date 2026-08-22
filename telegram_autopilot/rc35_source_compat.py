from __future__ import annotations

from urllib.parse import urlsplit

_ACCESS_HTTP_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 429")
_INSTALLED = False


def is_access_http_error(error: BaseException | str) -> bool:
    text = str(error)
    return any(marker in text for marker in _ACCESS_HTTP_MARKERS)


def source_feed_candidates(url: str) -> list[str]:
    """Return a small, bounded set of conventional public feed candidates."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return []
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return []

    origin = f"{parts.scheme}://{parts.hostname.casefold().rstrip('.')}"
    path = (parts.path or "/").rstrip("/")
    candidates: list[str] = []

    def add(value: str) -> None:
        if value and value not in candidates:
            candidates.append(value)

    if path:
        add(origin + path + "/feed")
        add(origin + path + "/rss.xml")
    add(origin + "/feed")
    add(origin + "/rss.xml")
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
        headers.update({"Accept-Encoding": "identity", "Connection": "keep-alive", "DNT": "1"})
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
                response = source_fetch(candidate, max_bytes=8 * 1024 * 1024, timeout=7)
                items = collector_module.parse_rss(response.body)
                if items:
                    return collector_module.SourceDetection(
                        "rss", response.final_url, collector_module._suggested_name(page_url, "rss")
                    )
            except Exception:
                continue
        return None

    def detect_source(value: str):
        normalized = collector_module.normalize_source_url(value)
        username = collector_module._telegram_username(normalized)
        if username:
            return collector_module.SourceDetection("telegram", f"https://t.me/{username}", "@" + username)

        parts = urlsplit(normalized)
        host = (parts.hostname or "").casefold().removeprefix("www.")
        if host == "reuters.com":
            raise collector_module.CollectorError(
                "Reuters зараз блокує автоматичний збір із reuters.com (HTTP 401) і не надає придатного "
                "публічного RSS/Atom для цього автопілота. Джерело не буде збережено як нібито робоче. "
                "Reuters прибрано з рекомендованого набору CTRL+UA."
            )

        try:
            return original_detect_source(normalized)
        except Exception as exc:
            if not is_access_http_error(exc):
                raise
            feed = try_feed(normalized)
            if feed is not None:
                return feed
            raise collector_module.CollectorError(
                "Сайт блокує автоматичну перевірку (HTTP 401/403/429), а придатний публічний RSS/Atom "
                "fallback не знайдено. Джерело не збережено, щоб не створювати фальшиво активний запис."
            ) from exc

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

    def source_detection_failed(win, button, status, error):
        if not win.winfo_exists():
            return
        button.configure(state="normal")
        text = str(error)
        if is_access_http_error(text) or "блокує автоматич" in text or "Reuters зараз" in text:
            status.set("🔴 Джерело недоступне для автоматичного збору.")
            ui_module.messagebox.showwarning(ui_module.APP_NAME, text, parent=win)
        else:
            status.set("Не вдалося перевірити джерело.")
            ui_module.messagebox.showerror(ui_module.APP_NAME, text, parent=win)

    collector_module._source_fetch = source_fetch
    collector_module._common_feed_candidates = common_feed_candidates
    collector_module.detect_source = detect_source
    collector_module.collect_source = collect_source
    ui_module.detect_source = detect_source
    service_module.collect_source = collect_source
    ui_module.MainWindow._source_detection_failed = staticmethod(source_detection_failed)

    _INSTALLED = True
