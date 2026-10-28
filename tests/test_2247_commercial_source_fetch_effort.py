"""2.2.47: live commercial throughput regression without cutting QA or source roster."""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import pytest

from telegram_autopilot import collector
from telegram_autopilot.models import Source
from telegram_autopilot.v2.commercial_fetch_effort_247 import commercial_page_fetch_limits
from telegram_autopilot.v2.freshness_fence_241 import source_freshness_rejection


def src(id, kind="page", priority=20):
    return SimpleNamespace(id=id, kind=kind, priority=priority, name=f"source-{id}")


def test_only_slow_zero_yield_page_uses_shallow_fetch():
    sources = [src(1), src(2), src(3), src(4, kind="rss"), src(5)]
    health = [
        {"source_id": 1, "last_duration_ms": 61125, "last_added": 0},
        {"source_id": 2, "last_duration_ms": 43717, "last_added": 0},
        {"source_id": 3, "last_duration_ms": 60000, "last_added": 1},
        {"source_id": 4, "last_duration_ms": 55000, "last_added": 0},
        {"source_id": 5, "last_duration_ms": 31000, "last_added": 0},
    ]
    cohort = [
        {"source_id": 1, "published": 0},
        {"source_id": 2, "published": 1},
        {"source_id": 3, "published": 0},
        {"source_id": 4, "published": 0},
        {"source_id": 5, "published": 0},
    ]
    result = commercial_page_fetch_limits(
        sources, health, cohort, page_fetch_limit=8, page_candidate_scan_limit=24
    )
    assert result == {1: (12, 4)}
    assert len(sources) == 5
    assert all(s.priority == 20 for s in sources)


def test_operator_shallow_settings_and_new_custom_sources_left_alone():
    sources = [src(77), src(78)]
    health = [
        {"source_id": 77, "last_duration_ms": 61125, "last_added": 0},
        {"source_id": 78, "last_duration_ms": 60000, "last_added": 0},
    ]
    result = commercial_page_fetch_limits(
        sources, health, [{"source_id": 77, "published": 0}],
        page_fetch_limit=4, page_candidate_scan_limit=8,
    )
    assert result == {}  # already shallow, and 78 has no proven cohort


def _source(kind="rss"):
    return Source(
        id=99, channel_id=2, kind=kind, name="Commercial feed",
        url="https://example.org/feed/", enabled=True, initialized=True,
        last_checked_at=None, last_error=None,
    )


@pytest.mark.parametrize("only_new", [True, False])
def test_rss_unneeded_hydration_skipped_but_source_records_kept(monkeypatch, only_new):
    old_date = "Mon, 26 Oct 2026 16:00:00 +0200"
    new_date = "Wed, 28 Oct 2026 11:45:00 +0200"
    rss = f"""<?xml version="1.0"?>
    <rss><channel>
    <item><title>Old commercial idea</title><link>https://example.org/old</link>
    <guid>old</guid><description>Old campaign context</description>
    <pubDate>{old_date}</pubDate></item>
    <item><title>Brand-new consumer campaign</title><link>https://example.org/new</link>
    <guid>new</guid><description>A real source-supported fact</description>
    <pubDate>{new_date}</pubDate></item>
    </channel></rss>""".encode("utf-8")
    seen = []
    monkeypatch.setattr(collector, "_source_fetch", lambda *args, **kwargs: SimpleNamespace(body=rss))
    def hydrate(item, **kwargs):
        seen.append(item.external_id)
        item.raw_text = "Full text from the same source page" * 15
        return item
    monkeypatch.setattr(collector, "_enrich_article", hydrate)
    kwargs = {}
    if only_new:
        kwargs["rss_enrich_eligible"] = (
            lambda item: not source_freshness_rejection(
                item.published_at, "2026-10-28T10:28:26+02:00",
                now=datetime(2026, 10, 28, 12, 0, tzinfo=timezone(timedelta(hours=2))),
            )
        )
        # Fixture's time is 11:45, and runtime is earlier that day.
    rows = collector.collect_source(_source(), **kwargs)
    assert {row.external_id for row in rows} == {"old", "new"}
    assert seen == (["new"] if only_new else ["old", "new"])


def test_http_403_is_not_bypassed_or_mislabeled_as_valid_story(monkeypatch):
    from telegram_autopilot.network import NetworkError
    def blocked(*args, **kwargs):
        raise NetworkError("Remote request failed with HTTP 403")
    monkeypatch.setattr(collector, "_source_fetch", blocked)
    with pytest.raises(collector.CollectorError):
        collector.collect_source(_source("rss"), rss_enrich_eligible=lambda _: True)


def test_public_site_fallback_still_requires_real_feed(monkeypatch):
    from telegram_autopilot.network import NetworkError
    calls = []
    def blocked(*args, **kwargs):
        calls.append(args[0])
        raise NetworkError("Remote request failed with HTTP 403")
    monkeypatch.setattr(collector, "_source_fetch", blocked)
    with pytest.raises(collector.CollectorError):
        collector.collect_source(
            _source("page"),
            page_prefer_feed=True,
            rss_enrich_eligible=lambda _: True,
        )
    assert len(calls) >= 2


def test_no_editorial_or_user_settings_modified():
    import inspect
    import telegram_autopilot.v2.commercial_fetch_effort_247 as module
    src = inspect.getsource(module)
    assert "UPDATE sources" not in src
    assert "UPDATE channels" not in src
    assert "PUBLISHED" not in src.upper() or "published" in src
