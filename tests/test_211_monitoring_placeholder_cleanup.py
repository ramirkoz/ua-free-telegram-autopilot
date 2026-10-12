"""Monitoring final-editor regression: drop invented system-link promises only."""
from telegram_autopilot.v2.publisher import strip_monitoring_system_placeholders as clean


def test_exact_operator_phrase_removed_without_touching_article():
    original = ("Групи інвалідності: порядок встановлення та строки.\n\n"
                "Докладні умови наведено в інформаційних картках.\n\n"
                "Деталі — у картках за посиланням, яке додасть система.")
    assert clean(original) == ("Групи інвалідності: порядок встановлення та строки.\n\n"
                               "Докладні умови наведено в інформаційних картках.")


def test_real_link_and_useful_card_text_preserved():
    original = ("Деталі — у картках за посиланням: https://example.gov.ua/cards\n"
                "Інформаційні картки додаються до цього допису.")
    assert clean(original) == original


def test_no_edit_to_normal_detail_sentences():
    text = "Деталі — у картках.\nДеталі — у повідомленні сільської ради."
    assert clean(text) == text


def test_remove_only_offending_line_not_other_content():
    text = "Перший абзац.\n\nДеталі — у картках за посиланням, яке додасть система.\n\nОстанній абзац."
    assert clean(text) == "Перший абзац.\n\nОстанній абзац."
