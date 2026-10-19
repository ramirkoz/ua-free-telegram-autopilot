"""Regression for operator 19 October Zaporizhzhia rejection leak."""
from telegram_autopilot.v2.publication_safety import is_ai_rejection_text


def test_exact_operator_rejection_never_publishable():
    assert is_ai_rejection_text("Відповідь:\n\nЦей матеріал не стосується Запорізької області, тому не відповідає тематиці каналу.")


def test_relevant_casualty_news_is_not_a_rejection():
    assert not is_ai_rejection_text("У Запоріжжі внаслідок удару БПЛА загинули шестеро людей, серед них троє дітей, повідомила ОВА.")


def test_rejection_patterns():
    assert is_ai_rejection_text("Ця новина не відповідає тематиці каналу.")
    assert is_ai_rejection_text("Матеріал відхилено: не підходить для каналу.")
    assert not is_ai_rejection_text("У Запоріжжі відкрили новий центр підтримки сімей.")
