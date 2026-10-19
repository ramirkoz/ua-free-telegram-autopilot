"""2.2.3 observability for commercial throughput.

Operator case (18.10, ПРОДАНО!): 0 publications all day, 8/8 rejected in the
last 2 h, 5 sources blocked by HTTP 403, yet the channel showed HEALTHY at
21:13 because the publish window (07:00-21:00) had just closed.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.v2 import editorial
from telegram_autopilot.v2.supervisor import SupervisorConfig, SupervisorService


def _service(monkeypatch, *, window_open: bool = False, elapsed_today: float = 14 * 3600.0):
    """Deterministic clock: by default the 21:13 situation (window closed, 14 h elapsed)."""
    monkeypatch.setattr(SupervisorService, "_publish_window_open_seconds",
                        staticmethod(lambda _s, _n: (window_open, 3 * 3600.0 if window_open else 0.0)))
    monkeypatch.setattr(SupervisorService, "_publish_window_elapsed_today",
                        staticmethod(lambda _s, _n: elapsed_today))
    supervisor = object.__new__(SupervisorService)
    supervisor.store = SimpleNamespace(get_channel=lambda _cid: None)
    return supervisor


def _snapshot(**stats):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=3)).isoformat()
    base = {
        "name": "ПРОДАНО!", "due_jobs": 0, "last_job_activity": old, "ready": 0,
        "ready_publishable": 0, "ready_permanent_blocked": 0, "published_60m": 0,
        "sources_total": 31, "sources_cooling_down": 5, "max_age_hours": 24,
        "publish_start": "07:00", "publish_end": "21:00",
        "output_starvation_enabled": True, "output_starvation_window_hours": 2,
        "output_starvation_min_processed": 5, "output_starvation_min_published": 1,
        "jobs_done_starvation_window": 8, "published_starvation_window": 0,
        "published_today": 0, "jobs_done_today": 42,
        "blocked_sources": [{"name": "Little Black Book", "consecutive_failures": 12},
                            {"name": "The Dieline", "consecutive_failures": 12}],
    }
    base.update(stats)
    return {
        "runtime_started_at": old,
        "channels": {"2": {"alive": True, "collector_alive": True, "phase": "idle",
                           "heartbeat_at": now.isoformat(), "last_job_activity_at": old}},
        "channel_stats": {"2": base},
    }


def test_window_elapsed_today_counts_a_window_that_already_closed():
    stats = {"publish_start": "07:00", "publish_end": "21:00"}
    evening = datetime(2026, 10, 18, 21, 13).astimezone()
    morning = datetime(2026, 10, 18, 6, 30).astimezone()
    assert SupervisorService._publish_window_elapsed_today(stats, evening) == 14 * 3600
    assert SupervisorService._publish_window_elapsed_today(stats, morning) == 0


def test_zero_publications_today_is_degraded_even_after_window_closed(monkeypatch):
    service = _service(monkeypatch)
    state = service._operational_states(_snapshot(), SupervisorConfig())["2"]
    assert state["state"] == "DEGRADED"
    assert state["day_output_starved"] is True
    assert any("no publications today" in reason for reason in state["reasons"])


def test_channel_that_published_today_is_not_day_starved(monkeypatch):
    service = _service(monkeypatch)
    state = service._operational_states(_snapshot(published_today=3), SupervisorConfig())["2"]
    assert state["day_output_starved"] is False


def test_blocked_sources_are_notices_not_degradation(monkeypatch):
    service = _service(monkeypatch, elapsed_today=0.0)
    state = service._operational_states(_snapshot(published_today=2), SupervisorConfig())["2"]
    assert state["state"] == "HEALTHY"
    assert state["notices"] and "Little Black Book" in state["notices"][0]


def test_selector_reject_code_is_structured_and_counted():
    source = inspect.getsource(editorial)
    assert '"reject_code"' in source
    assert set(editorial.SELECTOR_REJECT_CODES) >= {"weak_audience_hook", "weak_mechanism", "off_topic", "other"}
    category = SupervisorService._commercial_reject_category
    assert category("[weak_mechanism] Звичайна кампанія без незвичної механіки чи широкого гачка") == "weak_commercial_mechanism"
    assert category("[off_topic] B2B hiring announcement") == "off_topic"
    assert category("SOLD_VALUE_REJECT score=41; code=below_sold_value; ...") == "below_commercial_value"
    # Legacy uncoded reasons keep the old lexical fallback.
    assert category("Немає сильного вірусного гачка для широкої аудиторії") == "weak_broad_audience_hook"


def test_commercial_snapshot_has_a_24h_view():
    source = inspect.getsource(SupervisorService._commercial_throughput_snapshot)
    assert "window_24h" in source
    report = inspect.getsource(SupervisorService._commercial_day_report)
    for key in ("processed", "published", "reject_categories", "media_required_permanent", "ready_waiting_for_media"):
        assert key in report
