from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.v2.ingest import _stale_at_ingest, IngestService, CollectedArticle

NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


def test_channel_age_window_is_authoritative():
    old = (NOW - timedelta(hours=48)).isoformat()
    assert _stale_at_ingest(old, 24, now=NOW)
    assert not _stale_at_ingest(old, 72, now=NOW)


def test_recent_timezone_and_boundary_survive():
    recent = (NOW - timedelta(hours=23)).astimezone(timezone(timedelta(hours=3))).isoformat()
    assert not _stale_at_ingest(recent, 24, now=NOW)
    assert not _stale_at_ingest(NOW.isoformat(), 24, now=NOW)


def test_uncertain_date_must_not_create_false_rejections():
    for date in ('', None, 'not-a-date', '2026-10-12 10:00:00'):
        assert not _stale_at_ingest(date, 24, now=NOW)


def test_historical_dated_news_filtered():
    assert _stale_at_ingest('2024-10-13T13:00:00+03:00', 24, now=NOW)
    assert _stale_at_ingest('2022-02-01T10:00:00Z', 24, now=NOW)


def test_future_dated_items_are_not_discarded_as_old():
    assert not _stale_at_ingest((NOW + timedelta(minutes=15)).isoformat(), 24, now=NOW)
