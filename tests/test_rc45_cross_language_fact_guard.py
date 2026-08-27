import pytest

from telegram_autopilot.fact_guard import FactGuardError
from telegram_autopilot import rc45_policy
from telegram_autopilot.rc45_fact_guard import install_rc45_fact_guard


def _source(text: str):
    return {"title": "Українська лабораторія тестує роботів", "raw_text": text}


def test_rc45_cross_language_guard_allows_normal_english_translation_vocabulary():
    install_rc45_fact_guard()
    article = _source(
        (
            "Українська лабораторія повідомила про експериментальну систему для навчання роботів. "
            "Дослідники записують рухи людей і наголошують, що результат поки не гарантований. "
            "Проєкт залишається на етапі випробувань і не описується як перший у світі. "
        ) * 3
    )
    output = (
        "A Ukrainian robotics lab is testing a system that uses recorded human movement to train machines for physical tasks. "
        "Researchers say the project is still experimental and its success is not guaranteed."
    )
    assessment = rc45_policy.validate_fact_guard(article, output)
    assert assessment.checked_entities == 0


def test_rc45_cross_language_guard_blocks_unsupported_first_ever_claim():
    install_rc45_fact_guard()
    article = _source(
        (
            "Українська лабораторія тестує систему для навчання роботів на записах рухів людей. "
            "Команда описує роботу як експеримент і не робить заяв про світовий пріоритет. "
        ) * 4
    )
    output = (
        "A Ukrainian robotics lab has built the world's first system for training robots from recorded human movement. "
        "The team is testing the approach."
    )
    with pytest.raises(FactGuardError):
        rc45_policy.validate_fact_guard(article, output)


def test_rc45_cross_language_guard_blocks_plan_becoming_purchase():
    install_rc45_fact_guard()
    article = _source(
        (
            "Компанія підписала угоду про майбутнє розгортання системи та планує спільну розробку. "
            "Партнери описують наступний етап як технічну інтеграцію і випробування. "
        ) * 4
    )
    output = "The company acquired the system under an agreement and plans to deploy it later."
    with pytest.raises(FactGuardError):
        rc45_policy.validate_fact_guard(article, output)
