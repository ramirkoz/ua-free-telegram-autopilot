"""v2.2.51: source/draft/final meaning and Ukrainian non-guess language checks."""
import pytest
from telegram_autopilot.v2.final_claim_delta_251 import (
    FINAL_CLAIM_REVIEW_RULE, draft_final_regressions,
)
from telegram_autopilot.v2.ukrainian_agreement_245 import high_confidence_agreement_issues


def codes(draft, final):
    return {x.code for x in draft_final_regressions(draft, final)}


def test_science_final_editor_cannot_upgrade_same_hypothesis():
    draft = (
        "Дослідники припускають, що подвійну структуру кілець "
        "утримують планетарні тіла. Результат ще перевіряють."
    )
    final = "Подвійну структуру кілець утримують планетарні тіла. Результат ще перевіряють."
    assert "EDITORIAL_CERTAINTY_ESCALATION_251" in codes(draft, final)


def test_qualified_final_is_safe():
    a = "Дослідники припускають, що кільця утримують залишки планетарних тіл."
    b = "За припущенням дослідників, кільця утримують залишки планетарних тіл."
    assert codes(a, b) == set()


def test_qualified_statement_removed_entirely_is_not_conflated():
    a = "Ймовірно, давню планетарну систему зруйнувала зоря. Вчені знайшли два кільця уламків."
    b = "Вчені знайшли два кільця уламків."
    assert codes(a, b) == set()


def test_unrelated_hypothesis_does_not_contaminate_observed_finding():
    a = "Дослідники виявили кам'янисті уламки. Можливо, частина з них належить планеті."
    b = "Дослідники виявили кам'янисті уламки. Частину досліджують далі."
    assert codes(a, b) == set()


def test_no_false_upgrade_of_factual_reporting():
    a = "Бренд випустив рекламну кампанію. У ній використано традиційну анімацію."
    b = "Бренд представив рекламну кампанію з традиційною анімацією."
    assert codes(a, b) == set()


def test_promoting_animation_contribution_to_film_authorship_is_blocked():
    a = "Аніматор працював над «Королем Левом» і «Мулан». Він долучився до команди кампанії."
    b = "Аніматор став автором «Короля Лева» і «Мулан». Він долучився до команди кампанії."
    assert "EDITORIAL_ROLE_PROMOTION_251" in codes(a, b)


def test_not_every_brand_author_is_film_credit_error():
    a = "Команда працювала над «Королем Левом». Бренд створив кампанію «Зима»."
    b = "Команда працювала над «Королем Левом». Автором кампанії «Зима» став бренд."
    assert "EDITORIAL_ROLE_PROMOTION_251" not in codes(a, b)


def test_grammar_case_from_real_post_is_blocked():
    err = "Спостереження дають змогу побачити майбутнє нашої власної планетні системи."
    assert any("UK_CASE" in x for x in high_confidence_agreement_issues(err))


@pytest.mark.parametrize("good", [
    "Спостереження дають змогу побачити майбутнє нашої планетної системи.",
    "Астрономи виявили дві планетні системи.",
    "Дослідники описали планетні системи навколо двох зірок.",
])
def test_case_guard_does_not_block_correct_genders(good):
    assert not any("UK_CASE" in x for x in high_confidence_agreement_issues(good))


def test_rules_preserve_source_as_factual_authority():
    assert "may/might/could" in FINAL_CLAIM_REVIEW_RULE
    assert "SOURCE" in FINAL_CLAIM_REVIEW_RULE
    assert "працював" in FINAL_CLAIM_REVIEW_RULE.casefold()


def test_service_possibility_is_not_a_science_hypothesis():
    a = "Фонд розповів про можливість отримати допомогу онлайн."
    b = "Фонд надає можливість отримати допомогу онлайн."
    assert codes(a, b) == set()
