from __future__ import annotations

from telegram_autopilot import collector
from telegram_autopilot import rc35_source_compat as compat
from telegram_autopilot.network import HttpResponse


def _restore_installed(originals):
    collector._source_fetch = originals["collector_source_fetch"]
    collector.detect_source = originals["collector_detect_source"]
    collector.collect_source = originals["collector_collect_source"]
    collector._common_feed_candidates = originals["collector_common_feed_candidates"]
    originals["ui"].detect_source = originals["ui_detect_source"]
    originals["service"].collect_source = originals["service_collect_source"]
    compat._INSTALLED = False


def _snapshot():
    from telegram_autopilot import service, ui

    return {
        "collector_source_fetch": collector._source_fetch,
        "collector_detect_source": collector.detect_source,
        "collector_collect_source": collector.collect_source,
        "collector_common_feed_candidates": collector._common_feed_candidates,
        "ui": ui,
        "ui_detect_source": ui.detect_source,
        "service": service,
        "service_collect_source": service.collect_source,
    }


def test_reuters_technology_has_explicit_feed_candidates():
    rows = compat.source_feed_candidates("https://www.reuters.com/technology/")
    assert rows
    assert any("feeds.reuters.com/reuters/technologyNews" in row for row in rows)
    assert len(rows) == len(set(rows))


def test_source_fetch_retries_http_401_with_browser_navigation_headers(monkeypatch):
    originals = _snapshot()
    calls = []

    def fake_fetch(url, *, headers=None, **kwargs):
        calls.append(dict(headers or {}))
        if len(calls) == 1:
            raise collector.NetworkError(
                "Remote request failed with HTTP 401: https://www.reuters.com/technology/"
            )
        return HttpResponse(200, {"content-type": "text/html"}, b"<html></html>", url)

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        response = collector._source_fetch("https://www.reuters.com/technology/", timeout=1)
        assert response.status == 200
        assert len(calls) == 2
        assert calls[1]["Sec-Fetch-Mode"] == "navigate"
        assert calls[1]["Sec-Fetch-Dest"] == "document"
        assert calls[1]["Upgrade-Insecure-Requests"] == "1"
    finally:
        _restore_installed(originals)


def test_reuters_detection_uses_feed_alias_before_blocked_page(monkeypatch):
    originals = _snapshot()
    rss = b"""<?xml version='1.0'?><rss><channel><item><title>AI chip launch</title><link>https://www.reuters.com/technology/test-story/</link><guid>story-1</guid><description>Reuters technology story with enough context.</description></item></channel></rss>"""
    calls = []

    def fake_fetch(url, *, headers=None, **kwargs):
        calls.append(url)
        if "feeds.reuters.com/reuters/technologyNews" in url:
            return HttpResponse(200, {"content-type": "application/rss+xml"}, rss, url)
        raise collector.NetworkError(f"Remote request failed with HTTP 401: {url}")

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        detected = collector.detect_source("https://www.reuters.com/technology/")
        assert detected.kind == "rss"
        assert "feeds.reuters.com/reuters/technologyNews" in detected.url
        assert calls
        assert calls[0].startswith("https://feeds.reuters.com/")
        assert "https://www.reuters.com/technology/" not in calls
    finally:
        _restore_installed(originals)


def test_access_block_without_feed_does_not_block_saving_source(monkeypatch):
    originals = _snapshot()

    def fake_fetch(url, *, headers=None, **kwargs):
        raise collector.NetworkError(f"Remote request failed with HTTP 401: {url}")

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        detected = collector.detect_source("https://example.com/technology/")
        assert detected.kind == "page"
        assert detected.url == "https://example.com/technology/"
    finally:
        _restore_installed(originals)
