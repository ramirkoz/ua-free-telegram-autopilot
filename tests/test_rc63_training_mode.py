from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import telegram_autopilot.rc63_training_mode as rc63


class FakeDB:
    def __init__(self, last: str = ""):
        self.last = last

    def last_published_at(self, channel_id: int) -> str:
        return self.last


class FakeService:
    def __init__(self, db: FakeDB):
        self.db = db


def channel(*, cid: int = 1, name: str = "CTRL+UA", min_gap: int = 25):
    return SimpleNamespace(id=cid, name=name, min_publish_interval_minutes=min_gap)


def test_training_mode_has_no_daily_or_rolling_count_gate(monkeypatch):
    monkeypatch.setattr(
        "telegram_autopilot.rc62_editorial_control._is_marketing_channel",
        lambda db, cid, ch=None: False,
    )
    now = datetime(2026, 9, 2, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB((now - timedelta(hours=2)).isoformat()))

    reason, until = rc63.publication_hold_reason(service, channel(), now=now)

    assert reason == ""
    assert until is None


def test_ctrl_spacing_remains_60_minutes(monkeypatch):
    monkeypatch.setattr(
        "telegram_autopilot.rc62_editorial_control._is_marketing_channel",
        lambda db, cid, ch=None: False,
    )
    now = datetime(2026, 9, 2, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB((now - timedelta(minutes=35)).isoformat()))

    reason, until = rc63.publication_hold_reason(service, channel(), now=now)

    assert reason == "spacing"
    assert until == now + timedelta(minutes=25)


def test_marketing_spacing_remains_90_minutes(monkeypatch):
    monkeypatch.setattr(
        "telegram_autopilot.rc62_editorial_control._is_marketing_channel",
        lambda db, cid, ch=None: True,
    )
    now = datetime(2026, 9, 2, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB((now - timedelta(minutes=70)).isoformat()))

    reason, until = rc63.publication_hold_reason(
        service, channel(cid=2, name="ПРОДАНО!"), now=now
    )

    assert reason == "spacing"
    assert until == now + timedelta(minutes=20)


def test_quiet_hours_still_hold_without_count_caps(monkeypatch):
    monkeypatch.setattr(
        "telegram_autopilot.rc62_editorial_control._is_marketing_channel",
        lambda db, cid, ch=None: False,
    )
    now = datetime(2026, 9, 2, 3, 17, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB(""))

    reason, until = rc63.publication_hold_reason(service, channel(), now=now)

    assert reason == "quiet_hours"
    assert until == datetime(2026, 9, 2, 7, 0, tzinfo=now.tzinfo)
