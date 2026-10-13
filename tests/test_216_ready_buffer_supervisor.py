"""RC216: intentional, healthy READY buffer is not a stalled queue."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.v2.supervisor import SupervisorConfig, SupervisorService


def _snapshot(*, ready_publishable=2, phase="publish", fresh=True, published=1):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=1)).isoformat()
    heartbeat = (now if fresh else now - timedelta(hours=1)).isoformat()
    return {
        "runtime_started_at": old,
        "channels": {"1": {
            "alive": True, "collector_alive": True,
            "phase": phase, "heartbeat_at": heartbeat,
            "last_job_activity_at": old,
        }},
        "channel_stats": {"1": {
            "name": "CTRL+UA", "due_jobs": 45,
            "last_job_activity": old,
            "ready": 2, "ready_publishable": ready_publishable,
            "ready_permanent_blocked": 0,
            "published_60m": published,
            "sources_total": 0,
            "max_age_hours": 24,
        }},
    }


def _state(snapshot):
    supervisor = object.__new__(SupervisorService)
    return supervisor._operational_states(snapshot, SupervisorConfig())["1"]["state"]


def test_full_ready_buffer_and_healthy_worker_not_stalled():
    assert _state(_snapshot()) != "STALLED"


def test_without_publishable_buffer_still_stalled():
    assert _state(_snapshot(ready_publishable=0)) == "STALLED"


def test_stale_worker_heartbeat_still_stalled():
    assert _state(_snapshot(fresh=False)) == "STALLED"


def test_no_recent_publication_still_stalled():
    assert _state(_snapshot(published=0)) == "STALLED"
