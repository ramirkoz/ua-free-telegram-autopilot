"""v2.2.64: known listing links must not crowd out unseen commercial articles."""
from types import SimpleNamespace

from telegram_autopilot import collector
from telegram_autopilot.models import Source


def _source():
    return Source(
        id=126, channel_id=2, kind="page", name="Famous Campaigns",
        url="https://www.famouscampaigns.com/2026/", enabled=True,
        initialized=True, last_checked_at=None, last_error=None,
    )


def test_known_high_ranked_links_do_not_exhaust_page_scan(monkeypatch):
    old = "".join(
        f'<a href="/2026/11/known-campaign-story-{i:02d}-with-a-long-headline">'
        f'Known campaign about a brand with memorable artwork number {i:02d}</a>'
        for i in range(30)
    )
    fresh = "".join(
        f'<a href="/2026/11/fresh-campaign-story-{i:02d}-with-a-long-headline">'
        f'Fresh original campaign about an unexpected new idea number {i:02d}</a>'
        for i in range(2)
    )
    fetched = []
    eligible_urls = []

    monkeypatch.setattr(
        collector, "_source_fetch",
        lambda *args, **kwargs: SimpleNamespace(body=(old + fresh).encode()),
    )

    def enrich(item, **kwargs):
        fetched.append(item.url)
        item.raw_text = "Original source article with a specific real campaign story. " * 8
        return item

    monkeypatch.setattr(collector, "_enrich_article", enrich)

    def eligible(url):
        eligible_urls.append(url)
        return "/fresh-" in url

    result = collector.collect_source(
        _source(), page_candidate_scan_limit=8, page_fetch_limit=2,
        page_url_eligible=eligible,
    )
    assert len(result) == 2
    assert len(fetched) == 2
    assert all("/fresh-" in u for u in fetched)
    assert len(eligible_urls) > 8


def test_page_novelty_scan_bounded_and_does_not_fetch_known_urls(monkeypatch):
    links = "".join(
        f'<a href="/2026/11/known-campaign-story-{i:03d}-with-a-long-headline">'
        f'Known brand campaign with an extensive long title number {i:03d}</a>'
        for i in range(300)
    )
    monkeypatch.setattr(
        collector, "_source_fetch",
        lambda *args, **kwargs: SimpleNamespace(body=links.encode()),
    )
    seen = []

    def forbidden(*args, **kwargs):
        raise AssertionError("known article hydrated")

    monkeypatch.setattr(collector, "_enrich_article", forbidden)
    result = collector.collect_source(
        _source(), page_candidate_scan_limit=8, page_fetch_limit=2,
        page_url_eligible=lambda url: (seen.append(url) or False),
    )
    assert result == []
    assert 0 < len(seen) <= 48
