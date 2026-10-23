"""Regression: reader-first editorial quality contract based on the actual Content Tool pattern."""
from telegram_autopilot.v2.reader_first import (
    READER_FIRST_NEWSROOM_RULES, COMMERCIAL_READER_RULES, MONITORING_READER_RULES,
    FINAL_READER_REVIEW, writer_reader_rules, final_reader_rules,
    requires_final_reader_copyedit,
)


def test_content_tool_reader_first_core_applies_to_both_modes():
    for contract in (
        writer_reader_rules(monitoring=False, commercial=False),
        writer_reader_rules(monitoring=False, commercial=True),
        writer_reader_rules(monitoring=True, commercial=False),
    ):
        assert "ПЕРШЕ РЕЧЕННЯ" in contract
        assert "SOURCE" in contract
        assert "Не склеюй" in contract
        assert "не вигадуй" in contract.lower()


def test_commercial_newsroom_keeps_real_mechanism_not_trend_essay():
    commercial = writer_reader_rules(monitoring=False, commercial=True)
    assert COMMERCIAL_READER_RULES in commercial
    assert "хто випустив" in commercial
    assert "споживчі коди" in commercial
    assert "не приписуй дії одного іншому" in commercial
    assert "передзамовлення" in commercial
    assert MONITORING_READER_RULES not in commercial


def test_monitoring_keeps_practical_proven_news_without_commercial_moral():
    monitoring = writer_reader_rules(monitoring=True, commercial=False)
    assert MONITORING_READER_RULES in monitoring
    assert "практичні дії" in monitoring
    assert COMMERCIAL_READER_RULES not in monitoring
    assert "SOURCE" in final_reader_rules(monitoring=True, commercial=False)


def test_final_editor_is_required_for_every_editorial_candidate():
    assert requires_final_reader_copyedit(monitoring=False, legacy_quality_risk=False)
    assert requires_final_reader_copyedit(monitoring=False, legacy_quality_risk=True)
    assert not requires_final_reader_copyedit(monitoring=True, legacy_quality_risk=False)
    assert requires_final_reader_copyedit(monitoring=True, legacy_quality_risk=True)


def test_final_copyeditor_must_rebuild_confusing_draft_from_source():
    assert "ПЕРЕБУДУЙ" in FINAL_READER_REVIEW
    assert "причинні зв'язки" in FINAL_READER_REVIEW
    assert "відполіруй" in FINAL_READER_REVIEW
    assert COMMERCIAL_READER_RULES in final_reader_rules(monitoring=False, commercial=True)
    assert READER_FIRST_NEWSROOM_RULES not in final_reader_rules(monitoring=False, commercial=True)
