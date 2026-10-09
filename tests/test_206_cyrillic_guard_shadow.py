from telegram_autopilot.fact_guard import (
    CYRILLIC_ENTITY_GUARD_MODE,
    _cyrillic_entity_mismatches,
    validate_fact_guard,
)


def test_fpv_transliteration_does_not_invent_model():
    article = {
        "source_name": "Місцевий канал",
        "title": "Застосовано ФПВ-дрон",
        "raw_text": "У Запоріжжі повідомили про застосування ФПВ-дрона.",
    }
    validate_fact_guard(article, "У Запоріжжі повідомили про застосування FPV-дрона.")


def test_changed_ukrainian_acronym_visible_in_shadow():
    assert CYRILLIC_ENTITY_GUARD_MODE == "shadow"
    assert "МОВА" in _cyrillic_entity_mismatches(
        "Запорізька ЗОВА повідомила про пошкодження.",
        "МОВА повідомила про пошкодження.",
    )


def test_identical_acronym_not_flagged():
    assert _cyrillic_entity_mismatches(
        "ЗОВА повідомила про пошкодження.",
        "ЗОВА повідомила про пошкодження.",
    ) == ()
