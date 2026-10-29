"""Autopilot v2.2.54: real three post examples, source-scoped tone, no QA regressions."""
import inspect

from telegram_autopilot.ukrainian_quality import apply_safe_ukrainian_fixes
from telegram_autopilot.v2.editorial_tone_254 import (
    editorial_tone_kind, editorial_tone_rules,
)
from telegram_autopilot.v2.editorial import EditorialEngine


def article(title, raw):
    return {"title": title, "raw_text": raw}


def test_1624_real_sapper_farewell_is_memorial_not_impersonal_alert():
    a = article(
        "На Хортиці попрощалися із загиблим сапером",
        "Володимир Сороколат, 41-річний сапер Національної гвардії України, "
        "загинув у Донецькій області. На Хортиці відбулася церемонія "
        "прощання, захисника поховали на кладовищі рідного села."
    )
    assert editorial_tone_kind(a, monitoring=True) == "memorial"
    guidance = editorial_tone_rules(a, monitoring=True)
    assert "стриманий" in guidance
    assert "чоловік служив" in guidance
    assert "Не додавати вигаданих подвигів" in guidance
    assert "не міняти" in guidance.lower()


def test_military_fatality_report_is_not_automatically_memorial():
    a = article(
        "Атака дрона: загинув військовослужбовець",
        "Військовослужбовець загинув під час виконання завдання."
    )
    assert editorial_tone_kind(a, monitoring=True) == "general"
    assert "ПРОЩАННЯ" not in editorial_tone_rules(a, monitoring=True)


def test_generic_civilian_obituary_does_not_assume_defender_identity():
    a = article("Попрощалися із загиблим містянином",
                "У місті відбулося прощання із загиблим цивільним чоловіком.")
    assert editorial_tone_kind(a, monitoring=True) == "general"


def test_1623_real_japanese_folding_pavilion_has_design_hook():
    a = article(
        "Japan dobedo studio ehho!2 collapsible pavilion",
        "Японська студія створила переносний павільйон: дерев'яні боки "
        "розкладаються у лавки. Використали дерево від розібраного сараю."
    )
    assert editorial_tone_kind(a, commercial=True) == "design_transform"
    prompt = editorial_tone_rules(a, commercial=True)
    assert "перший абзац" in prompt
    assert "конкретну цікаву механіку" in prompt
    assert "Не вигадуй екологічного ефекту" in prompt


def test_design_object_without_transformation_is_not_recast_as_transforming():
    a = article("Нова лавка", "У парку встановили нову лавку.")
    assert editorial_tone_kind(a, commercial=True) == "general"
    assert "ДИЗАЙН / ТРАНСФОРМАЦІЯ" not in editorial_tone_rules(a, commercial=True)


def test_noncommercial_story_cannot_inherit_commercial_design_style():
    a = article("В укритті поставили лавку", "Встановили лавку, яка розкладається.")
    assert editorial_tone_kind(a, monitoring=True) == "general"


def test_1609_bats_science_distinguishes_correlation_from_causation():
    a = article("Madagascar bats are shrinking",
                "The study finds a correlation rather than demonstrating causation.")
    assert editorial_tone_kind(a, science=True) == "science"
    guidance = editorial_tone_rules(a, science=True)
    assert "причинно-наслідкового зв'язку" in guidance
    assert "ЛИШЕ якщо" in guidance
    assert "точні числа" in guidance


def test_no_automatic_overstatement_of_hunting_intensity():
    a = article("Fruit bats", "They are hunted on plantations.")
    assert editorial_tone_kind(a, science=True) == "science"
    assert apply_safe_ukrainian_fixes("На них полюють у промислових обсягах.") == (
        "На них полюють у промислових обсягах."
    )
    # An unsupported intensity must be left to the SOURCE-driven model/Fact Guard,
    # not silently recast as another factual quantity.


def test_narrow_grammar_fix_preserves_claim_and_other_text():
    text = "Дослідження встановлює кореляцію, а не доказує причинність: клімат також міг вплинути."
    out = apply_safe_ukrainian_fixes(text)
    assert "не доводить причинно-наслідкового зв’язку" in out
    assert "клімат також міг вплинути" in out
    assert "не доказує причинність" not in out
    other = "Дослідження не доказує рівність формул."
    assert apply_safe_ukrainian_fixes(other) == other


def test_final_tone_guidance_cannot_invent_extra_facts():
    a = article("Прощання з військовим", "Загинув сапер. Сьогодні поховали.")
    guidance = editorial_tone_rules(a, monitoring=True, final=True)
    assert "не змінюй дат, учасників, чисел" in guidance
    assert "вигаданих подвигів" in guidance


def test_writer_and_final_editor_both_use_tone_with_unmodified_qa():
    writer = inspect.getsource(EditorialEngine.write)
    final = inspect.getsource(EditorialEngine._final_edit)
    assert "editorial_tone_rules(" in writer and "{tone_rule}" in writer
    assert "editorial_tone_rules(" in final and "final=True" in final
    assert "validate_writer_output(" in writer and "validate_writer_output(" in final
    assert "draft_final_regressions(" in final
