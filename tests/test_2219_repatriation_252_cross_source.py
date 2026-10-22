"""Source-owned cross-source 252-event regression from live operator evidence."""
from telegram_autopilot.v2.repatriation_event_identity import (
    repatriation_same_event, national_repatriation_without_local_outcome,
)
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


def row(text, source_id, when, *, published=False):
    return {
        "channel_id": 3, "source_id": source_id,
        "title": text, "raw_text": text,
        "source_published_at": "" if published else when,
        "published_at": when if published else "",
        "discovered_at": when,
    }


FIRST = "В Україну повернули тіла 252 військових, повідомив Коордштаб."
SECOND = "В Україну повернули тіла ще 252 людей, які належать військовослужбовцям, повідомив Координаційний штаб."
DATE1 = "2026-10-22T13:00:34+03:00"
DATE2 = "2026-10-22T13:17:07+03:00"


def test_two_operators_sources_are_same_event():
    a, b = row(FIRST, 197, DATE1), row(SECOND, 191, DATE2)
    assert repatriation_same_event(b, a)[0]
    assert event_fingerprint_same_event(b, a)[0]
    assert event_fingerprint_same_event(b, row(FIRST, 197, "2026-10-22T13:30:31+03:00", published=True))[0]


def test_different_count_and_day_remain_separate():
    a = row(FIRST, 197, DATE1)
    b = row(SECOND.replace("252", "253"), 191, DATE2)
    c = row(SECOND, 191, "2026-10-23T13:17:07+03:00")
    assert not event_fingerprint_same_event(b, a)[0]
    assert not event_fingerprint_same_event(c, a)[0]


def test_national_vs_local_outcome():
    a = row(FIRST, 197, DATE1)
    local = row("У Запоріжжі ідентифікували воїна серед повернутих тіл 252 військових.", 191, DATE2)
    assert national_repatriation_without_local_outcome(a)
    assert not national_repatriation_without_local_outcome(local)
    assert not repatriation_same_event(a, local)[0]


def test_unrelated_same_number():
    a = row(FIRST, 197, DATE1)
    b = row("У Запоріжжі 252 мешканці отримали допомогу.", 191, DATE2)
    assert not repatriation_same_event(b, a)[0]
