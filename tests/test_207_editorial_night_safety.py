from __future__ import annotations

from telegram_autopilot.v2.editorial import _source_grounding_night_issues
from telegram_autopilot.ukrainian_quality import final_language_blockers


def _article(raw: str):
    return {"source_name": "ЗАПОРІЖЖЯ.ІНФО", "title": "", "raw_text": raw}


def test_short_blast_not_transformed_to_confirmed_attack():
    source = _article("❗ Олександрівський, фпв. Вибух був.")
    output = "В Олександрівській громаді пролунав вибух. За попередньою інформацією, це сталося через атаку ворожого FPV-дрона."
    issues = _source_grounding_night_issues(source, output)
    assert any("причину" in x for x in issues)
    assert any("походження" in x for x in issues)
    assert any("атрибуція" in x for x in issues)


def test_short_incident_without_invented_cause_passes():
    source = _article("❗ Олександрівський, фпв. Вибух був.")
    assert not _source_grounding_night_issues(source, "В Олександрівському повідомили про вибух.")


def test_explicit_source_causality_is_not_removed():
    source = _article("Унаслідок атаки російського FPV-дрона пролунав вибух.")
    assert not _source_grounding_night_issues(
        source, "Пролунав вибух через атаку російського FPV-дрона."
    )


def test_unsupported_cause_not_rejected_when_source_is_large():
    source = _article("У громаді повідомили про вибух. " + "Уточнення. " * 80)
    assert not _source_grounding_night_issues(source, "Пролунав вибух через атаку FPV-дрона.")


def test_low_quality_calque_blocks_publication():
    assert any("низькокачесні" in issue for issue in final_language_blockers(
        "Низькокачесні Android-смартфони постачаються з небажаними додатками."
    ))


def test_normal_ukrainian_equivalent_not_blocked():
    assert not final_language_blockers("Деякі недорогі Android-смартфони мають шкідливі застосунки.")
