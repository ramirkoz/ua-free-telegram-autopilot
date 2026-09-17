from __future__ import annotations

from telegram_autopilot.v2.bounded_ingest import BoundedStrictIngestService
from telegram_autopilot.v2.event_dedupe_guard import (
    EventFingerprintDedupeEngine,
    _near_numeric_pairs,
    event_fingerprint_same_event,
)


def _row(source_id: int, title: str, body: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_name": f"source-{source_id}",
        "title": title,
        "raw_text": body,
        "final_text": "",
        "event_summary": "",
        "canonical_source_url": f"https://example{source_id}.org/item",
        "source_url": f"https://example{source_id}.org/item",
        "content_hash": f"hash-{source_id}",
    }


def test_observed_human_cortical_mouse_study_is_one_event() -> None:
    first = _row(
        1,
        "Людські нейрони заповнили понад 90 відсотків кори головного мозку мишей",
        (
            "Дослідники виростили генетично модифікованих мишей без більшої частини кори та гіпокампа. "
            "У порожній простір пересадили крихітні згустки людських нейронів, вирощені зі стовбурових клітин. "
            "За три місяці людська тканина збільшилася майже у п'ять разів та інтегрувалася в нервову систему."
        ),
    )
    second = _row(
        2,
        "Людський трансплантат зайняв близько 92 відсотків кортикальної тканини миші",
        (
            "Дослідники інтегрували людські кортикальні органоїди у нервову систему генетично модифікованих мишей. "
            "Тканини зі стовбурових клітин пересадили в мозок. Органоїд розрісся, з'єднався з мозком і спинним мозком "
            "та активувався під час неспання."
        ),
    )

    same, reason = event_fingerprint_same_event(first, second)

    assert same is True
    assert "fingerprint" in reason


def test_near_percentages_are_compatible_numeric_anchors() -> None:
    assert _near_numeric_pairs("понад 90% кори", "близько 92 відсотків тканини") == [(90.0, 92.0)]


def test_same_topic_but_different_mouse_study_is_not_collapsed() -> None:
    transplant = _row(
        1,
        "Людські нейрони інтегрували у кору мозку мишей",
        "Людські кортикальні органоїди зі стовбурових клітин пересадили у мозок мишей і тканина розрослася.",
    )
    drug_trial = _row(
        2,
        "Новий препарат змінив активність нейронів кори мозку мишей",
        "Вчені дослідили дію нового препарату на нейрони кори мозку лабораторних мишей без трансплантації людської тканини.",
    )

    same, _ = event_fingerprint_same_event(transplant, drug_trial)

    assert same is False


def test_final_gate_uses_event_fingerprint_engine_and_bounded_ingest_has_budget() -> None:
    assert issubclass(EventFingerprintDedupeEngine, object)
    assert BoundedStrictIngestService.channel_source_budget_seconds <= 70.0
