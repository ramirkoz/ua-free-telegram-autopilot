from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import telegram_autopilot.rc64_live_tuning as rc64


class FakeDB:
    def __init__(self, last: str = ""):
        self.last = last

    def last_published_at(self, channel_id: int) -> str:
        return self.last


class FakeService:
    def __init__(self, db: FakeDB):
        self.db = db


def channel(cid: int = 1, name: str = "CTRL+UA"):
    return SimpleNamespace(id=cid, name=name, min_publish_interval_minutes=90)


def test_rc64_replaces_editorial_spacing_with_five_minute_technical_gap():
    now = datetime(2026, 9, 3, 10, 0, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB((now - timedelta(minutes=4)).isoformat()))

    reason, until = rc64.publication_hold_reason(service, channel(), now=now)

    assert reason == "technical_spacing"
    assert until == now + timedelta(minutes=1)


def test_rc64_ignores_old_channel_90_minute_setting_after_five_minutes():
    now = datetime(2026, 9, 3, 10, 0, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB((now - timedelta(minutes=6)).isoformat()))

    reason, until = rc64.publication_hold_reason(service, channel(name="ПРОДАНО!"), now=now)

    assert reason == ""
    assert until is None


def test_rc64_keeps_quiet_hours():
    now = datetime(2026, 9, 3, 3, 20, tzinfo=timezone(timedelta(hours=3)))
    service = FakeService(FakeDB(""))

    reason, until = rc64.publication_hold_reason(service, channel(), now=now)

    assert reason == "quiet_hours"
    assert until == datetime(2026, 9, 3, 7, 0, tzinfo=now.tzinfo)


def test_rc64_detects_cross_source_same_event_from_strong_headlines():
    now = datetime.now(timezone.utc)
    row = {
        "id": 10,
        "title": "A strange decagon swirls around Saturn's south pole",
        "published_at": (now - timedelta(hours=10)).isoformat(),
    }

    hit = rc64._strong_title_event(
        "Saturn has a big weird decagon around its south pole",
        row,
    )

    assert hit is not None
    assert hit[0] >= 0.9


def test_rc64_does_not_apply_broad_title_rule_to_old_story():
    now = datetime.now(timezone.utc)
    row = {
        "id": 10,
        "title": "A strange decagon swirls around Saturn's south pole",
        "published_at": (now - timedelta(hours=50)).isoformat(),
    }

    assert rc64._strong_title_event(
        "Saturn has a big weird decagon around its south pole",
        row,
    ) is None


def test_name_localization_gate_finds_human_names_but_not_formula_only():
    assert rc64._needs_name_localization("Michael J Fox і Harrison Ford записали ролик.")
    assert rc64._needs_name_localization("Телескоп Hubble побачив структуру.")
    assert not rc64._needs_name_localization("У NbSe2 і TaS2 бачать дві електронні зони.")


def test_marketing_selector_can_rescue_broad_behavioral_story(monkeypatch):
    result = SimpleNamespace(text='''{"decision":"publish","fit_score":79,"reason":"є механіка","angle":"як інтерфейс змінює витрати","topic_tags":["retail"],"human_interest_score":78,"creative_surprise_score":35,"marketing_mechanic_score":65,"friend_share_score":70,"non_marketer_hook":"люди витрачають більше через дизайн"}''')
    rejected = {
        "decision": "reject",
        "fit_score": 79,
        "reason": "RC62 HUMAN_INTEREST_REJECT: test",
        "angle": "",
        "topic_tags": ["retail"],
        "human_interest_score": 78,
        "creative_surprise_score": 35,
        "marketing_mechanic_score": 65,
        "friend_share_score": 70,
        "non_marketer_hook": "люди витрачають більше через дизайн",
    }

    monkeypatch.setattr(rc64, "_PREV_SELECTOR", lambda policy, article, channel_id=0: (result, rejected))
    monkeypatch.setattr("telegram_autopilot.rc62_editorial_control._marketing", lambda policy: True)

    _result, parsed = rc64._run_selector_rc64(SimpleNamespace(), {"id": 77}, channel_id=2)

    assert parsed["decision"] == "publish"
    assert parsed["reason"].startswith("RC64 BROAD_HUMAN_INTEREST_PASS")
