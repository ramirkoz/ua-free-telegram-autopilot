"""v2.3.21 regressions from operator-scored November 9 samples.

All synthetic/test-only: no network, Telegram send or operator Data mutation.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.v2.editorial_operator_2321 import (
    concrete_routine_pr_reason, verify_low_confidence_publish,
)
from telegram_autopilot.v2.editorial_feedback_2320 import calibrated_feedback_2320
from telegram_autopilot.v2.freshness_fence_241 import restart_source_rejection
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event

KYIV = timezone(timedelta(hours=2))


def test_editorial_recent_last_night_survives_local_midnight():
    now = datetime(2026, 11, 9, 0, 10, tzinfo=KYIV)
    started = "2026-11-08T18:26:27+02:00"
    source = "2026-11-08T23:45:53+02:00"
    discovered = "2026-11-08T23:56:38+02:00"
    assert restart_source_rejection(
        source, started, "", discovered_at=discovered,
        now=now, rolling_window_hours=24,
    ) == ""
    # Monitoring keeps the preexisting calendar-day policy.
    assert restart_source_rejection(
        source, started, "", discovered_at=discovered, now=now,
    ) == "SOURCE_NOT_CURRENT_DAY"


def test_editorial_rolling_window_does_not_replay_old_backlog():
    now = datetime(2026, 11, 9, 11, 15, tzinfo=KYIV)
    started = "2026-11-09T10:15:00+02:00"
    assert restart_source_rejection(
        "2026-11-08T11:00:00+02:00", started, "",
        discovered_at="2026-11-09T10:30:00+02:00",
        now=now, rolling_window_hours=24,
    ) == "SOURCE_TOO_OLD_2321"
    assert restart_source_rejection(
        "2026-11-09T09:00:00+02:00", started, "",
        discovered_at="2026-11-09T10:30:00+02:00",
        now=now, rolling_window_hours=24,
    ) == "SOURCE_PREDATES_RUNTIME_START"
    assert restart_source_rejection(
        "2026-11-09T10:30:00+02:00", started, "",
        discovered_at="2026-11-09T10:10:00+02:00",
        now=now, rolling_window_hours=24,
    ) == "SOURCE_DISCOVERY_UNVERIFIED_2321"


def test_restart_checkpoint_crossing_midnight_still_bounded():
    now = datetime(2026, 11, 9, 0, 15, tzinfo=KYIV)
    args = ("2026-11-08T23:59:00+02:00", "2026-11-09T00:02:00+02:00")
    assert restart_source_rejection(
        *args, "2026-11-08T23:55:00+02:00",
        discovered_at="2026-11-09T00:05:00+02:00",
        now=now, rolling_window_hours=24,
    ) == ""
    assert restart_source_rejection(
        *args, "2026-11-08T12:00:00+02:00",
        discovered_at="2026-11-09T00:05:00+02:00",
        now=now, rolling_window_hours=24,
    ) == "SOURCE_PREDATES_RUNTIME_START"


def test_only_unrealized_agency_appointments_get_narrow_veto():
    appointment = {
        "title": "Pilpel appoints Banter as lead agency",
        "raw_text": ("An agency has been appointed to develop a future creative "
                     "platform. The first work is expected to be unveiled next month."),
    }
    assert concrete_routine_pr_reason(appointment, "creative") == (
        "EDITOR_2321_UNREALIZED_AGENCY_APPOINTMENT"
    )
    activation = {
        "title": "Heineken opens a remote taproom in new brand activation",
        "raw_text": "Heineken opened a taproom on a remote trail. Visitors can try the installation.",
    }
    assert concrete_routine_pr_reason(activation, "creative") == ""
    assert concrete_routine_pr_reason(appointment, "science") == ""


def test_ambiguous_publish_requires_source_review_not_score_hard_filter():
    useful = {"title": "World's largest sand desert reveals ancient climate findings"}
    mundane = {"title": "Disadvantages of buying tech from other countries"}
    # 2.3.23: a numeric score no longer triggers the vetoing review (the old
    # template made models echo fit_score 0..19 for wanted stories too).
    assert not verify_low_confidence_publish("science", 12, useful)
    assert not verify_low_confidence_publish("science", 12, mundane)
    assert not verify_low_confidence_publish("science", 70, useful)
    # Concrete source-evidenced risk patterns are still reviewed.
    assert verify_low_confidence_publish(
        "creative", 90, {"title": "Brand X appoints Agency Y as lead creative agency"})
    assert not verify_low_confidence_publish("monitoring", 12, useful)
    assert "41" in calibrated_feedback_2320("science")
    assert "20" in calibrated_feedback_2320("creative")


def test_unrelated_agency_and_calendar_are_not_the_same_event():
    agency = {
        "source_id": 129, "title": "Growing an independent agency without growing headcount",
        "source_url": "https://campaignbrief.com/growing-an-independent-agency-without-growing-headcount/",
        "raw_text": ("Growing an independent agency without growing headcount. "
                     "Here is an essay about hiring and agency strategy. "
                     "Without new staff, this business uses artificial intelligence. "
                     "Here is more context about independent client service."),
    }
    calendar = {
        "source_id": 199, "title": "A $20 Paper Calendar Holds Three Months Without a Separate Stand",
        "source_url": "https://www.yankodesign.com/2026/11/08/a-paper-calendar/",
        "raw_text": ("A paper calendar displays three months at once. "
                     "Here is a desk object without a stand. "
                     "Without wasting space, the triangular calendar is useful. "
                     "Here is a design available for twenty dollars."),
    }
    same, reason = event_fingerprint_same_event(
        agency, calendar, commercial_profile=True,
    )
    assert not same, reason
