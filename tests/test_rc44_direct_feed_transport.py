from __future__ import annotations

import pytest

from telegram_autopilot import collector
from telegram_autopilot.network import HttpResponse, NetworkError
from telegram_autopilot import rc44_source_transport as rc44


RSS = b"""<?xml version='1.0'?><rss><channel><item><title>Evidence-based science story</title><link>https://example.com/story</link><guid>story-1</guid><description>Enough context for a valid feed item.</description></item></channel></rss>"""


def test_rc44_source_fetch_uses_system_transport_after_access_block(monkeypatch):
    original = collector._source_fetch
    calls = []

    def blocked(url, **kwargs):
        raise NetworkError(f"Remote request failed with HTTP 403: {url}")

    def curl_ok(url, **kwargs):
        calls.append((url, kwargs))
        return HttpResponse(200, {"content-type": "application/rss+xml"}, RSS, url)

    monkeypatch.setattr(collector, "_source_fetch", blocked)
    monkeypatch.setattr(rc44, "curl_public_fetch", curl_ok)
    rc44._INSTALLED = False
    try:
        rc44.install_rc44_source_transport()
        response = collector._source_fetch(
            "https://example.com/feed/latest/",
            max_bytes=12345,
            timeout=7,
            allowed_content_types={"application/rss+xml"},
        )
        assert response.body == RSS
        assert calls[0][0] == "https://example.com/feed/latest/"
        assert calls[0][1]["max_bytes"] == 12345
        assert calls[0][1]["timeout"] == 7.0
    finally:
        collector._source_fetch = original
        rc44._INSTALLED = False


def test_rc44_does_not_bypass_non_access_network_errors(monkeypatch):
    original = collector._source_fetch
    calls = []

    def failed(url, **kwargs):
        raise NetworkError("DNS resolution failed for example.com.")

    monkeypatch.setattr(collector, "_source_fetch", failed)
    monkeypatch.setattr(rc44, "curl_public_fetch", lambda *args, **kwargs: calls.append(1))
    rc44._INSTALLED = False
    try:
        rc44.install_rc44_source_transport()
        with pytest.raises(NetworkError, match="DNS resolution failed"):
            collector._source_fetch("https://example.com/feed")
        assert calls == []
    finally:
        collector._source_fetch = original
        rc44._INSTALLED = False


def test_rc44_header_parser_accepts_http2_style_status():
    status, headers = rc44._parse_headers(
        b"HTTP/2 200\r\ncontent-type: application/rss+xml; charset=utf-8\r\ncache-control: max-age=60\r\n\r\n"
    )
    assert status == 200
    assert headers["content-type"].startswith("application/rss+xml")
