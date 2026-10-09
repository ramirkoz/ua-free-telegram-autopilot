from __future__ import annotations

from telegram_autopilot.v2.editorial import _unsupported_analysis_claims


def _article(text: str, title: str = ""):
    return {"title": title, "raw_text": text, "source_name": "Source"}


def test_208_no_invented_preliminary_attribution():
    issues = _unsupported_analysis_claims(
        _article("У громаді підтвердили, що за минулу добу було атаковано два об'єкти."),
        "За попередньою інформацією, атакували два об'єкти.",
    )
    assert issues


def test_208_no_invented_analysis_from_short_news():
    assert _unsupported_analysis_claims(
        _article("Уряд опублікував оновлені правила."),
        "Це свідчить про нову епоху цифровізації.",
    )


def test_208_actual_preliminary_evidence_is_preserved():
    assert not _unsupported_analysis_claims(
        _article("Preliminary reports say the rocket hit the launch pad."),
        "За попередньою інформацією, ракета влучила у стартовий майданчик.",
    )


def test_208_english_source_suggests_not_blocked():
    assert not _unsupported_analysis_claims(
        _article("This suggests that attackers exploited the second vulnerability."),
        "Це свідчить про використання другої вразливості.",
    )


def test_208_normal_factual_rewrite_unaffected():
    assert not _unsupported_analysis_claims(
        _article("За минулу добу громада зазнала двох атак."),
        "Протягом минулої доби громаду атакували двічі.",
    )
