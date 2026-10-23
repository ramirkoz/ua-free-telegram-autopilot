"""2.2.26 operator-facing source safety and conservative event expansion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.source_fact_integrity import (
    fatality_numbers, source_fact_issues, non_overridable_quality_issues,
)
from telegram_autopilot.v2.event_memory import _facts, _relation


def _row(raw: str, *, title: str = "") -> dict:
    return {"id": 75930, "raw_text": raw, "title": title,
            "source_url": "https://t.me/official/4656"}


def _incoming(aid: int, text: str, *, offset_minutes: int = 0, channel: int = 3,
              title: str = "") -> dict:
    when = (datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)).isoformat()
    return {"id": aid, "channel_id": channel, "raw_text": text, "title": title,
            "source_published_at": when, "published_at": ""}


SOURCE = "Росіяни обстріляли приватний будинок у Запоріжжі. Загинули двоє людей."
BAD = "Після обстрілу приватного будинку у Запоріжжі загинули троє людей. Про наслідки повідомила влада."
GOOD = "У Запоріжжі обстріляли приватний будинок. Унаслідок удару загинули двоє людей."


def test_explicit_casualty_number_must_come_from_source():
    assert fatality_numbers(SOURCE) == frozenset({2})
    assert source_fact_issues(_row(SOURCE), BAD) == ("FACT_UNSUPPORTED_FATALITY_COUNT",)
    assert source_fact_issues(_row(SOURCE), GOOD) == ()


def test_source_correction_contains_old_and_new_counts():
    original = ("Внаслідок удару загинули двоє людей. "
                "Пізніше кількість загиблих зросла до трьох.")
    assert 2 in fatality_numbers(original)
    assert 3 in fatality_numbers(original)
    assert not source_fact_issues(_row(original), BAD)


def test_fatality_unknown_or_number_unrelated_to_deaths_does_not_fabricate():
    original = "Поранено троє людей на вулиці Перемоги. Рятувальники працюють."
    assert not source_fact_issues(_row(original), BAD)
    assert fatality_numbers("На будинку номер 3. Загинули двоє людей.") == frozenset({2})


def test_non_overridable_hard_fact_gate_for_human_and_automated():
    channel = SimpleNamespace(mode=ChannelMode.MONITORING)
    issues = non_overridable_quality_issues(channel, _row(SOURCE), BAD)
    assert "FACT_UNSUPPORTED_FATALITY_COUNT" in issues
    assert not non_overridable_quality_issues(channel, _row(SOURCE), GOOD)


def test_unsettled_aerial_not_allowed_even_for_human_approved():
    channel = SimpleNamespace(mode=ChannelMode.MONITORING)
    row = _row("Реактивний об’єкт пролетів через мости. Триває спостереження.")
    output = "Мости перекрили через загрозу. Рух відновлять найближчим часом."
    assert "MONITORING_UNSETTLED_AERIAL_SOURCE" in non_overridable_quality_issues(channel, row, output)


def test_human_approval_never_monkeypatches_global_editorial_gate(monkeypatch):
    from telegram_autopilot.v2 import editorial, runtime_contracts
    from telegram_autopilot.v2.publisher import Publisher

    original_gate = editorial.prepublish_quality_issues
    seen = []

    class FakeStore:
        def get_article(self, article_id):
            return {"channel_id": 3}

    def fake_publish(self, article_id, heartbeat=None):
        seen.append((self._rc102_human_approved, self._rc102_force_publish,
                     editorial.prepublish_quality_issues is original_gate))
        return "PUBLISHED"

    monkeypatch.setattr(Publisher, "can_publish_now", lambda self, channel_id: (True, "OK"))
    monkeypatch.setattr(Publisher, "publish_one", fake_publish)
    monkeypatch.setattr(runtime_contracts, "_human_approved", lambda store, article_id: True)
    runtime_contracts._install_publisher_contract()
    publisher = object.__new__(Publisher)
    publisher.store = FakeStore()
    assert publisher.publish_one(5, force=True) == "PUBLISHED"
    assert seen == [(True, True, True)]
    assert editorial.prepublish_quality_issues is original_gate
    assert publisher._rc102_human_approved is False


ACT = ("Мелітопольська міська рада ухвалила рішення від 23.10.2026 №104. "
       "Документ оприлюднено на офіційному сайті.")
REPEAT = ("Мелітопольська міська рада оприлюднила рішення від 23.10.2026 №104. "
          "Його ухвалили на засіданні.")


def test_same_dated_numbered_council_act_repeats_across_sources():
    earlier = _incoming(10, ACT, offset_minutes=150, title=ACT)
    duplicate = _incoming(11, REPEAT, offset_minutes=145)
    assert _facts(earlier)["family"] == "municipal_act"
    assert _relation(duplicate, earlier) == "DUPLICATE"
    assert _relation(_incoming(12, REPEAT, offset_minutes=60*51), earlier) == ""


def test_municipal_identity_never_merges_different_authority_or_new_progress():
    earlier = _incoming(10, ACT, offset_minutes=90)
    other = REPEAT.replace("Мелітопольська", "Бердянська")
    different_number = REPEAT.replace("№104", "№105")
    follow_up = REPEAT + " Місто розпочало виплати за рішенням."
    assert _relation(_incoming(11, other), earlier) == ""
    assert _relation(_incoming(12, different_number), earlier) == ""
    assert _relation(_incoming(13, follow_up), earlier) == ""


def test_municipal_requires_unambiguous_act_council_and_document_date():
    unknown = "Міська рада ухвалила рішення про фінансування. Про це повідомила пресслужба."
    two_acts = ACT + " Ухвалено рішення від 23.10.2026 №105."
    assert _facts(_incoming(1, unknown)) == {}
    assert _facts(_incoming(2, two_acts)) == {}
