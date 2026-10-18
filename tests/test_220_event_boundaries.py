from telegram_autopilot.v2.event_boundaries import classify_event_boundaries
from telegram_autopilot.v2.evidence_first import assess_monitoring_source
from types import SimpleNamespace


def test_distinct_animal_and_document_notices_have_source_spans():
    source = ("Біля школи приблудився хаскі. "
              "На вулиці Василя Сергієнка загубили папку з документами.")
    decision = classify_event_boundaries(source)
    assert decision.ambiguous
    assert {"lost_animal", "lost_property"}.issubset(decision.categories)
    assert all(source[item.start:item.end] == item.evidence for item in decision.spans)
    article = SimpleNamespace(title="Оголошення", raw_text=source)
    assert "MONITORING_MULTIPLE_UNRELATED_NOTICES" in assess_monitoring_source(article).reasons


def test_legitimate_community_event_keeps_single_context():
    source = ("У громаді відбулася арттерапевтична зустріч. "
              "Учасники малювали власні картини.")
    assert not classify_event_boundaries(source).ambiguous


def test_road_incident_and_unrelated_lost_item_are_not_one_story():
    source = ("На греблі сталася ДТП. На сусідній вулиці загубили ключі.")
    result = classify_event_boundaries(source)
    assert result.ambiguous
    assert {"road_incident", "lost_property"}.issubset(result.categories)


def test_ambiguous_pronoun_without_source_proof_is_not_auto_resolved():
    result = classify_event_boundaries("Його шукають.")
    assert not result.ambiguous
    assert result.spans == ()
