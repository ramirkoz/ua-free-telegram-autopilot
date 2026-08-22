from __future__ import annotations

import pytest

from telegram_autopilot import collector
from telegram_autopilot import rc35_source_compat as compat
from telegram_autopilot.network import HttpResponse


def _restore_installed(originals):
    collector._source_fetch = originals["collector_source_fetch"]
    collector.detect_source = originals["collector_detect_source"]
    collector.collect_source = originals["collector_collect_source"]
    collector._common_feed_candidates = originals["collector_common_feed_candidates"]
    originals["ui"].detect_source = originals["ui_detect_source"]
    originals["ui"].MainWindow._source_detection_failed = originals["ui_detection_failed"]
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
        "ui_detection_failed": ui.MainWindow._source_detection_failed,
        "service": service,
        "service_collect_source": service.collect_source,
    }


def test_feed_candidates_are_bounded_and_section_first():
    rows = compat.source_feed_candidates("https://example.com/technology/")
    assert rows == [
        "https://example.com/technology/feed",
        "https://example.com/technology/rss.xml",
        "https://example.com/feed",
        "https://example.com/rss.xml",
    ]


def test_source_fetch_retries_http_401_with_navigation_headers(monkeypatch):
    originals = _snapshot()
    calls = []

    def fake_fetch(url, *, headers=None, **kwargs):
        calls.append(dict(headers or {}))
        if len(calls) == 1:
            raise collector.NetworkError("Remote request failed with HTTP 401: https://example.com/technology/")
        return HttpResponse(200, {"content-type": "text/html"}, b"<html></html>", url)

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        response = collector._source_fetch("https://example.com/technology/", timeout=1)
        assert response.status == 200
        assert len(calls) == 2
        assert calls[1]["Sec-Fetch-Mode"] == "navigate"
        assert calls[1]["Sec-Fetch-Dest"] == "document"
        assert calls[1]["Upgrade-Insecure-Requests"] == "1"
    finally:
        _restore_installed(originals)


def test_reuters_is_rejected_as_known_uncollectable_source(monkeypatch):
    originals = _snapshot()
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Reuters known-blocked path should fail before network probing")

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        with pytest.raises(collector.CollectorError, match="Reuters зараз блокує"):
            collector.detect_source("https://www.reuters.com/technology/")
        assert not calls
    finally:
        _restore_installed(originals)


def test_access_block_uses_public_feed_fallback(monkeypatch):
    originals = _snapshot()
    rss = b"""<?xml version='1.0'?><rss><channel><item><title>AI chip launch</title><link>https://example.com/story</link><guid>story-1</guid><description>Technology story with enough context for feed detection.</description></item></channel></rss>"""
    calls = []

    def fake_fetch(url, *, headers=None, **kwargs):
        calls.append(url)
        if url == "https://example.com/technology/feed":
            return HttpResponse(200, {"content-type": "application/rss+xml"}, rss, url)
        raise collector.NetworkError(f"Remote request failed with HTTP 401: {url}")

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        detected = collector.detect_source("https://example.com/technology/")
        assert detected.kind == "rss"
        assert detected.url == "https://example.com/technology/feed"
    finally:
        _restore_installed(originals)


def test_access_block_without_feed_is_not_saved_as_fake_active_source(monkeypatch):
    originals = _snapshot()

    def fake_fetch(url, *, headers=None, **kwargs):
        raise collector.NetworkError(f"Remote request failed with HTTP 401: {url}")

    monkeypatch.setattr(collector, "fetch_url", fake_fetch)
    compat._INSTALLED = False
    try:
        compat.install_rc35_source_compat()
        with pytest.raises(collector.CollectorError, match="Джерело не збережено"):
            collector.detect_source("https://example.com/technology/")
    finally:
        _restore_installed(originals)
