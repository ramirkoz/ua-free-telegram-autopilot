"""Regression: published Telegram text/captions are plain text, not Markdown."""
from telegram_autopilot.v2.publication_markup_2347 import (
    normalize_plaintext_markup_2347,
)


def test_real_live_psychology_of_music_case():
    body = "Такі результати отримали дослідники у журналі *Psychology of Music*."
    assert normalize_plaintext_markup_2347(body) == (
        "Такі результати отримали дослідники у журналі «Psychology of Music»."
    )


def test_inline_bold_and_italic_are_guillemets_in_plain_text():
    text = "У журналі **Nature** і в *Science* опублікували дослідження."
    assert normalize_plaintext_markup_2347(text) == (
        "У журналі «Nature» і в «Science» опублікували дослідження."
    )


def test_existing_title_line_bold_is_unwrapped_not_quoted():
    text = "**Важлива новина**\n\nУ журналі *Science* перевірили метод."
    assert normalize_plaintext_markup_2347(text) == (
        "Важлива новина\n\nУ журналі «Science» перевірили метод."
    )


def test_math_unpaired_stars_and_bullets_are_not_rewritten():
    text = "2*3=6, 5 * 6 * 7; * пункт списку; \u2605 зірка; *немає пари."
    assert normalize_plaintext_markup_2347(text) == text


def test_one_character_emphasis_and_escaped_literal():
    text = r"Класифікація *A* та \*B*."
    assert normalize_plaintext_markup_2347(text) == r"Класифікація «A» та \*B*."


def test_existing_ukrainian_quotes_and_real_names_unchanged():
    text = "Журнал «Psychology of Music» перевірив пам'ять; 3D-друк."
    assert normalize_plaintext_markup_2347(text) == text


def test_idempotent_and_multiline_mixed_article():
    text = "*Psychology of Music*\n\n**Ключовий результат** залежить від експерименту."
    expected = "«Psychology of Music»\n\n«Ключовий результат» залежить від експерименту."
    assert normalize_plaintext_markup_2347(text) == expected
    assert normalize_plaintext_markup_2347(expected) == expected


def test_no_unbounded_cross_paragraph_matching():
    text = "До першої зірочки *один абзац\n\nа тут *друга."
    assert normalize_plaintext_markup_2347(text) == text
