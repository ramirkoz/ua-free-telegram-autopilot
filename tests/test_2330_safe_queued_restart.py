"""2.3.30 restart continuity is deliberately narrower than old 24h replay."""
from datetime import datetime
import pytest

from telegram_autopilot.v2.carryover_ready_228 import (
    safe_same_day_queued_2330,
    safe_same_day_ready_228,
)

NOW = datetime.fromisoformat("2026-11-12T12:42:00+02:00")
START = "2026-11-12T12:37:12+02:00"
SOURCE = "2026-11-12T12:09:56+02:00"
DISCOVERED = "2026-11-12T12:13:40+02:00"
CHECKPOINT = "2026-11-12T12:29:00+02:00"


def test_2330_short_restart_pending_queued_is_not_lost():
    assert safe_same_day_queued_2330(SOURCE, DISCOVERED, START, CHECKPOINT, now=NOW)


def test_2330_ready_does_not_use_queued_exception_if_preboot():
    # Preboot READY has an independent strict rule and delivery preflight.
    assert safe_same_day_ready_228(
        SOURCE, DISCOVERED, "2026-11-12T12:28:00+02:00", START,
        now=NOW,
    )


@pytest.mark.parametrize("source,discovered,started,checkpoint,now", [
    ("2026-11-11T19:30:00+02:00", DISCOVERED, START, CHECKPOINT, NOW),
    ("2026-11-12T01:30:00+02:00", "2026-11-12T02:00:00+02:00", START, CHECKPOINT, NOW),
    (SOURCE, DISCOVERED, START, "", NOW),
    (SOURCE, DISCOVERED, START, "2026-11-12T12:38:00+02:00", NOW),
    (SOURCE, DISCOVERED, START, "2026-11-12T12:12:00+02:00", NOW),
    ("2026-11-12T12:40:00+02:00", DISCOVERED, START, CHECKPOINT, NOW),
    (SOURCE, "2026-11-12T12:40:00+02:00", START, CHECKPOINT, NOW),
    (SOURCE, DISCOVERED, "2026-11-12T15:00:00+02:00", CHECKPOINT, NOW),
    (SOURCE, DISCOVERED, START, CHECKPOINT, datetime.fromisoformat("2026-11-13T00:05:00+02:00")),
])
def test_2330_stale_or_uncertain_queued_stays_rejected(source, discovered, started, checkpoint, now):
    assert not safe_same_day_queued_2330(source, discovered, started, checkpoint, now=now)


def test_2330_replay_cannot_skip_durable_receipt_check_source_static():
    # Regression on the public runtime/publication paths: both must call
    # the same predicate and inspect delivery_journal(article_id) is None.
    from pathlib import Path
    import inspect
    from telegram_autopilot.v2 import runtime, publisher
    worker_source = inspect.getsource(runtime.RuntimeEngine._process_one)
    pub_source = inspect.getsource(publisher.Publisher.publish_one)
    for source in (worker_source, pub_source):
        assert "safe_same_day_queued_2330" in source
        assert "not self.store.delivery_journal(article_id)" in source
        assert "SOURCE_PREDATES_RUNTIME_START" in source
