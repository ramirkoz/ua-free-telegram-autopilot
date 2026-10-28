"""Live regression: the Telegram ownership adapter must accept commercial RSS kwargs."""
from __future__ import annotations

import pytest
from telegram_autopilot import collector
from telegram_autopilot.models import Source
from telegram_autopilot.v2 import bounded_ingest, telegram_ingest_policy as policy


def source(kind):
    return Source(
        id=77, channel_id=2, kind=kind, name="Live adapter test",
        url="https://example.org/feed/", enabled=True, initialized=True,
        last_checked_at=None, last_error=None,
    )


@pytest.mark.parametrize("kind", ["rss", "page"])
def test_bounded_scheduler_propagates_freshness_to_collector(monkeypatch, kind):
    calls = []
    monkeypatch.setattr(collector, "collect_source", lambda src, **kw: calls.append((src, kw)) or [])
    monkeypatch.setattr(bounded_ingest, "collect_strict", policy._collect_current)
    predicate = lambda item: bool(item.published_at)
    assert bounded_ingest.collect_strict(
        source(kind), page_prefer_feed=True,
        page_candidate_scan_limit=12, page_fetch_limit=4,
        rss_enrich_eligible=predicate,
    ) == []
    assert len(calls) == 1
    src, kwargs = calls[0]
    assert src.kind == kind
    assert kwargs["rss_enrich_eligible"] is predicate
    assert kwargs["page_candidate_scan_limit"] == 12
    assert kwargs["page_fetch_limit"] == 4


def test_noncommercial_original_collector_contract(monkeypatch):
    calls = []
    monkeypatch.setattr(collector, "collect_source", lambda src, **kw: calls.append(kw) or [])
    monkeypatch.setattr(bounded_ingest, "collect_strict", policy._collect_current)
    assert bounded_ingest.collect_strict(source("rss")) == []
    assert "rss_enrich_eligible" not in calls[0]


def test_telegram_reader_remains_isolated(monkeypatch):
    calls = []
    monkeypatch.setattr(policy, "collect_telegram_current", lambda src: calls.append(src.kind) or [])
    monkeypatch.setattr(
        collector, "collect_source",
        lambda *args, **kwargs: pytest.fail("Telegram may not reach page/RSS collector"),
    )
    monkeypatch.setattr(bounded_ingest, "collect_strict", policy._collect_current)
    assert bounded_ingest.collect_strict(source("telegram"), rss_enrich_eligible=lambda _: True) == []
    assert calls == ["telegram"]
