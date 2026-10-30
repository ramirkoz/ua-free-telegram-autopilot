"""v2.2.60: continuity only for unseen, recent same-day source articles."""
import inspect
from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.freshness_fence_241 import (
    restart_source_rejection, source_freshness_rejection,
)
from telegram_autopilot.v2.runtime import RuntimeEngine
from telegram_autopilot.v2.publisher import Publisher
from telegram_autopilot.v2.bounded_ingest import BoundedStrictIngestService

K = timezone(timedelta(hours=2))
NOW = datetime(2026, 10, 30, 16, 40, tzinfo=K)
START = "2026-10-30T16:30:00+02:00"
CHECK = "2026-10-30T16:17:00+02:00"
STORY = "2026-10-30T16:24:00+02:00"
DISCOVERED = "2026-10-30T16:30:20+02:00"


def test_short_gap_source_is_eligible_only_after_new_discovery():
    assert source_freshness_rejection(STORY, START, now=NOW) == "SOURCE_PREDATES_RUNTIME_START"
    assert restart_source_rejection(STORY, START, CHECK, now=NOW) == ""
    assert restart_source_rejection(STORY, START, CHECK, discovered_at=DISCOVERED, now=NOW) == ""
    assert restart_source_rejection(STORY, START, CHECK, discovered_at=CHECK, now=NOW) == "SOURCE_PREDATES_RUNTIME_START"


def test_checkpoint_does_not_rescue_old_or_unverified_sources():
    bad = [
        ("2026-10-30T16:15:00+02:00", CHECK),
        (STORY, "2026-10-30T13:00:00+02:00"),
        (STORY, ""),
        (STORY, START),
        (STORY, "2026-10-30T17:00:00+02:00"),
        ("", CHECK),
        ("2026-10-29T23:59:00+02:00", CHECK),
        ("2026-10-30T16:55:00+02:00", CHECK),
    ]
    for published, checkpoint in bad:
        assert restart_source_rejection(published, START, checkpoint, now=NOW) != ""


def test_post_start_items_preserve_original_freshness_rule():
    stamp = "2026-10-30T16:32:00+02:00"
    assert restart_source_rejection(stamp, START, "", now=NOW) == ""
    assert restart_source_rejection("2026-10-29T23:55:00+02:00", START, CHECK, now=NOW) == "SOURCE_NOT_CURRENT_DAY"


def test_no_old_ready_replay_across_second_upgrade():
    assert restart_source_rejection(
        STORY, "2026-10-30T16:37:00+02:00",
        "2026-10-30T16:34:00+02:00", discovered_at=DISCOVERED, now=NOW,
    ) != ""


def test_all_three_live_gates_consult_same_checkpoint():
    runtime_start = inspect.getsource(RuntimeEngine.start)
    worker = inspect.getsource(RuntimeEngine._process_one)
    publisher = inspect.getsource(Publisher.publish_one)
    collector = inspect.getsource(BoundedStrictIngestService.collect_channel)
    assert "runtime_source_restart_checkpoints_260" in runtime_start
    assert "restart_source_rejection" in worker
    assert "discovered_at=" in worker
    assert "restart_source_rejection" in publisher
    assert "discovered_at=" in publisher
    assert "restart_source_rejection" in collector
    assert "originally_prestart and previous_reason" in collector
    assert "source_freshness_rejection" in collector
    assert "_delivery_preflight" in publisher
