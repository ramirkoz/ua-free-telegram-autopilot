import pytest
from telegram_autopilot.v2.evidence_ledger import extract_source_evidence


def test_source_evidence_keeps_original_spans_and_uncertainty():
    source = "РСЗВ вдарило по Юр'ївці.\nПопередньо повідомляють про пошкодження."
    ledger = extract_source_evidence(source, "zaborzp/154499")
    assert ledger.source_spans_valid(source)
    assert len(ledger.entries) == 2
    assert ledger.entries[0].quote == "РСЗВ вдарило по Юр'ївці."
    assert not ledger.entries[0].uncertainty
    assert ledger.entries[1].uncertainty


def test_source_current_temporal_markers_are_recorded_not_added():
    source = "Зараз оголосили тривогу. Згодом повідомили про відбій."
    ledger = extract_source_evidence(source, "community/401")
    assert ledger.entries[0].current_time_reference
    assert not ledger.entries[1].current_time_reference
    assert ledger.source_spans_valid(source)


def test_evidence_requires_source_identity():
    with pytest.raises(ValueError):
        extract_source_evidence("Оголошення.", "")


def test_empty_source_produces_no_evidence():
    assert extract_source_evidence(" ", "channel/100").entries == ()
