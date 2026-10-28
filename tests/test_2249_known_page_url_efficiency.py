"""2.2.49: known-page network avoidance, real production hook and safety guards."""
from __future__ import annotations

from types import SimpleNamespace
import inspect

import pytest

from telegram_autopilot import collector
from telegram_autopilot.models import Source
from telegram_autopilot.v2 import bounded_ingest, strict_ingest, telegram_ingest_policy as policy
from telegram_autopilot.v2.commercial_fetch_effort_247 import commercial_page_fetch_limits


def src(kind="page"):
    return Source(
        id=202, channel_id=2, kind=kind, name="Creative campaigns",
        url="https://example.org/", enabled=True, initialized=True,
        last_checked_at=None, last_error=None,
    )


def test_known_pages_skip_expensive_fetch_but_new_page_is_collected(monkeypatch):
    html = b"""<html>
        <a href="/already-known-creative-ad-campaign-announcement">Known creative campaign launch</a>
        <a href="/just-launched-brand-product-campaign-announcement">New product campaign launch</a>
        <a href="/another-known-advertising-brand-campaign">Another known advertising campaign</a>
    </html>"""
    seen = []
    monkeypatch.setattr(collector, "_source_fetch", lambda *a, **kw: SimpleNamespace(body=html))
    def enrich(item, **kwargs):
        seen.append(item.url)
        item.raw_text = "Full source-grounded campaign report. " * 16
        return item
    monkeypatch.setattr(collector, "_enrich_article", enrich)
    known = {
        "https://example.org/already-known-creative-ad-campaign-announcement",
        "https://example.org/another-known-advertising-brand-campaign",
    }
    rows = collector.collect_source(src(), page_url_eligible=lambda url: url not in known)
    assert len(rows) == 1
    assert rows[0].url == "https://example.org/just-launched-brand-product-campaign-announcement"
    assert seen == [rows[0].url]


def test_noncommercial_default_does_not_skip_known_pages(monkeypatch):
    html = b'<html><a href="/already-known-creative-ad-campaign-announcement">Known creative campaign launch</a></html>'
    seen = []
    monkeypatch.setattr(collector, "_source_fetch", lambda *a, **kw: SimpleNamespace(body=html))
    def enrich(item, **kwargs):
        seen.append(item.url)
        item.raw_text = "Original article fact-filled text. " * 20
        return item
    monkeypatch.setattr(collector, "_enrich_article", enrich)
    assert len(collector.collect_source(src())) == 1
    assert len(seen) == 1


@pytest.mark.parametrize("kind", ["page", "rss", "telegram"])
def test_production_adapter_accepts_new_keyword_without_media_misrouting(monkeypatch, kind):
    if kind == "telegram":
        monkeypatch.setattr(policy, "collect_telegram_current", lambda s: [])
    calls = []
    monkeypatch.setattr(collector, "collect_source", lambda s, **kw: calls.append(kw) or [])
    monkeypatch.setattr(bounded_ingest, "collect_strict", policy._collect_current)
    marker = lambda url: True
    assert bounded_ingest.collect_strict(src(kind), page_url_eligible=marker) == []
    if kind == "page":
        assert len(calls) == 1 and calls[0]["page_url_eligible"] is marker
    elif kind == "rss":
        assert len(calls) == 1 and "page_url_eligible" not in calls[0]
    else:
        assert calls == []


def test_strict_adapter_stays_compatible(monkeypatch):
    calls = []
    monkeypatch.setattr(collector, "collect_source", lambda s, **kw: calls.append(kw) or [])
    marker = lambda url: True
    assert strict_ingest.collect_strict(src(), page_url_eligible=marker) == []
    assert calls[0]["page_url_eligible"] is marker


def test_slow_no_yield_source_retains_all_listing_candidates():
    s = SimpleNamespace(id=1, kind="page")
    h = {"source_id": 1, "last_added": 0, "last_duration_ms": 70125}
    y = {"source_id": 1, "published": 0}
    assert commercial_page_fetch_limits(
        [s], [h], [y], page_fetch_limit=20, page_candidate_scan_limit=72
    ) == {1: (72, 4)}
    assert commercial_page_fetch_limits(
        [s], [h], [{"source_id": 1, "published": 1}],
        page_fetch_limit=20, page_candidate_scan_limit=72,
    ) == {}


def test_operator_roster_cadence_media_and_factual_policy_are_untouched():
    source = inspect.getsource(bounded_ingest.BoundedStrictIngestService.collect_channel)
    assert 'commercial_profile and source.kind == "page"' in source
    assert "page_url_eligible" in source
    assert "UPDATE sources SET enabled" not in source
    assert "UPDATE channels SET" not in source
