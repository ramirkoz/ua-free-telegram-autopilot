"""Regression: 27 Oct CTRL+UA post passed grammar QA but failed human understanding."""
from telegram_autopilot.v2.reader_first import (
    SCIENCE_PLAIN_READER_RULES,
    SCIENCE_FINAL_READER_REVIEW,
    writer_reader_rules,
    final_reader_rules,
)
from telegram_autopilot.v2.science_reader_clarity_243 import science_plain_language_issue


BAD_OPERATOR_POST = (
    "Автор експерименту створив дві наукові статті за допомогою ШІ. "
    "Перша, згенерована безплатними версіями ChatGPT і Gemini, "
    "описувала дослідження, якого насправді не проводили.\n\n"
    "Другу статтю підготувала FARS — система, що поєднує мовні моделі "
    "з обчислювальним кластером. За 21 хвилину вона створила огляд літератури.\n\n"
    "У 2025 році понад 12% оглядів Nature Communications виявилися "
    "повністю створеними ШІ."
)


def test_operator_example_fails_closed_before_telegram():
    assert science_plain_language_issue(BAD_OPERATOR_POST).startswith(
        "SCIENCE_READER_LEAD:"
    )


def test_non_technical_result_first_post_is_not_blocked():
    copy = (
        "Штучний інтелект може створити переконливу наукову статтю "
        "про експеримент, якого не проводили. Це показала перевірка "
        "згенерованих текстів.\n\n"
        "Під час іншої перевірки знайшли непідтверджені посилання. "
        "Самі по собі акуратний стиль і список джерел не доводять "
        "достовірності тексту."
    )
    assert science_plain_language_issue(copy) == ""


def test_do_not_block_source_grounded_named_discovery():
    text = (
        "Автори дослідження виявили, що новий метод дозволяє "
        "побачити раніше невідомий тип клітин.\n\n"
        "Це підтвердили лабораторними спостереженнями."
    )
    assert science_plain_language_issue(text) == ""



def test_opaque_genetics_abbreviation_without_explanation_is_blocked():
    text = (
        "Генетики відтворили історію заселення островів за зразками ДНК. "
        "Дослідники вивчили спільних предків методом IBD."
    )
    assert science_plain_language_issue(text).startswith("SCIENCE_READER_ACRONYM:")
    assert "IBD" in science_plain_language_issue(text)


def test_familiar_science_names_and_explained_acronyms_are_allowed():
    assert science_plain_language_issue(
        "NASA представила нові знімки планети."
    ) == ""
    assert science_plain_language_issue(
        "Вчені застосували метод IBD (порівняння спільних ділянок ДНК)."
    ) == ""


def test_science_rules_strong_not_global():
    common = writer_reader_rules(monitoring=False, commercial=False)
    science = writer_reader_rules(monitoring=False, commercial=False, science=True)
    monitoring = writer_reader_rules(monitoring=True, commercial=False)
    final_science = final_reader_rules(monitoring=False, commercial=False, science=True)
    final_commercial = final_reader_rules(monitoring=False, commercial=True)
    assert SCIENCE_PLAIN_READER_RULES not in common
    assert SCIENCE_PLAIN_READER_RULES not in monitoring
    assert SCIENCE_PLAIN_READER_RULES in science
    assert "автор експерименту" in science.lower()
    assert SCIENCE_FINAL_READER_REVIEW in final_science
    assert SCIENCE_FINAL_READER_REVIEW not in final_commercial
    assert "не додавай" in final_science.lower()


def test_blank_and_valid_short_lead_do_not_crash():
    assert science_plain_language_issue("") == ""
    assert science_plain_language_issue("Вчені виявили нову планету.") == ""
