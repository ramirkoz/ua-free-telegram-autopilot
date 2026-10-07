from __future__ import annotations

from pathlib import Path

from telegram_autopilot.v2.feedback import AUTO_REFRESH_SECONDS, FeedbackRuntime
from telegram_autopilot.v2.storage import V2Store


class _Service:
    def refresh_channel(self, channel_id: int, *, force: bool = False):
        return {"configured": True, "checked": 0, "saved": 0, "error": "", "elapsed": 0.0}


def test_rc114_default_feedback_interval_is_three_hours(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "rc114.sqlite3")
    runtime = FeedbackRuntime(_Service(), store)
    assert AUTO_REFRESH_SECONDS == 3 * 60 * 60
    assert runtime.interval_seconds == 3 * 60 * 60


def test_rc114_feedback_interval_is_persisted_and_clamped(tmp_path: Path) -> None:
    path = tmp_path / "rc114.sqlite3"
    store = V2Store(path)
    runtime = FeedbackRuntime(_Service(), store)
    assert runtime.configure_interval(4 * 60 * 60) == 4 * 60 * 60
    runtime2 = FeedbackRuntime(_Service(), V2Store(path))
    assert runtime2.interval_seconds == 4 * 60 * 60
    assert runtime2.configure_interval(1) == 15 * 60
    assert runtime2.configure_interval(48 * 60 * 60) == 24 * 60 * 60


def test_rc114_status_snapshot_exposes_operator_fields(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "rc114.sqlite3")
    runtime = FeedbackRuntime(_Service(), store)
    snap = runtime.status_snapshot()
    assert snap["interval_seconds"] == 3 * 60 * 60
    assert "last_success" in snap
    assert "last_error" in snap
    assert "next_in_seconds" in snap
    assert snap["running"] is False
