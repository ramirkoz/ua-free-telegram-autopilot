from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.freshness_fence_241 import source_freshness_rejection


KYIV = timezone(timedelta(hours=2))
NOW = datetime(2026, 10, 27, 12, 40, tzinfo=KYIV)
STARTED = datetime(2026, 10, 27, 12, 6, tzinfo=KYIV).isoformat()


def test_reported_oct_13_telegram_repost_is_refused_on_oct_27():
    assert source_freshness_rejection(
        "2026-10-13T10:00:00+03:00", STARTED, now=NOW
    ) == "SOURCE_NOT_CURRENT_DAY"


def test_same_day_but_before_restart_is_refused():
    assert source_freshness_rejection(
        "2026-10-27T12:05:59+02:00", STARTED, now=NOW
    ) == "SOURCE_PREDATES_RUNTIME_START"


def test_after_restart_today_passes_and_utc_is_compared_correctly():
    assert source_freshness_rejection(
        "2026-10-27T10:07:00Z", STARTED, now=NOW
    ) == ""


def test_previous_day_even_within_24_hours_is_refused():
    midnight = datetime(2026, 10, 27, 0, 10, tzinfo=KYIV)
    started = datetime(2026, 10, 26, 23, 55, tzinfo=KYIV).isoformat()
    assert source_freshness_rejection(
        "2026-10-26T23:59:00+02:00", started, now=midnight
    ) == "SOURCE_NOT_CURRENT_DAY"


def test_missing_naive_or_corrupt_source_time_never_becomes_fresh_discovery():
    for value in ("", "27 жовтня", "2026-10-27T12:30:00", "not-a-date"):
        assert source_freshness_rejection(
            value, STARTED, now=NOW
        ) == "SOURCE_DATE_UNVERIFIED"


def test_future_source_clock_cannot_bypass_gate():
    assert source_freshness_rejection(
        "2026-10-27T13:00:00+02:00", STARTED, now=NOW
    ) == "SOURCE_DATE_IN_FUTURE"


def test_rfc2822_source_timestamp_supported():
    assert source_freshness_rejection(
        "Tue, 27 Oct 2026 12:11:00 +0200", STARTED, now=NOW
    ) == ""


def test_runtime_start_is_mandatory():
    assert source_freshness_rejection(
        "2026-10-27T12:10:00+02:00", "", now=NOW
    ) == "RUNTIME_START_UNVERIFIED"
