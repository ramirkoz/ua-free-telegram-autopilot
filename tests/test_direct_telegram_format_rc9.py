from __future__ import annotations

import inspect
import sqlite3

import pytest

from telegram_autopilot.media_pipeline import PreparedMedia, _hard_reject
from telegram_autopilot.models import Channel
from telegram_autopilot.production_pipeline_rc9 import MEDIA_POST_HARD_LIMIT, POST_HARD_LIMIT, TEXT_POST_HARD_LIMIT, build_rewrite_prompt, validate_rewrite
from telegram_autopilot.service import AutopilotService
from telegram_autopilot.telegram import TelegramError, build_post_text


def _channel() -> Channel:
    return Channel(1, "CTRL+UA", "@ctrlua", "Technology and science", True, False, 5, 0, 72, 24, 3, "x", "x")


def _row():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE x(id INTEGER,title TEXT,raw_text TEXT,source_published_at TEXT)")
    con.execute("INSERT INTO x VALUES(1,?,?,?)", (
        "Uber partners with Zipline on drone delivery",
        "Uber Eats and Zipline will start drone deliveries later this year in Dallas-Fort Worth. The companies target one million daily deliveries by 2029. Zipline has operated in Texas since 2025.",
        "2026-08-17T10:24:35-04:00",
    ))
    return con.execute("SELECT * FROM x").fetchone()


def test_production_service_has_no_telegraph_write_path():
    source = inspect.getsource(AutopilotService._process).casefold()
    assert "telegraph" not in source
    assert "create_page" not in source
    assert "читати повністю" not in source


def test_production_service_can_upload_only_one_photo_per_post():
    source = inspect.getsource(AutopilotService._process)
    assert source.count("send_prepared_photo(") == 1
    assert "send_publication(" not in source
    assert "sendMediaGroup" not in source


def test_click_to_follow_promo_is_never_valid_editorial_media():
    item = PreparedMedia(
        1, "image", "https://cdn.example.com/google-follow-card.jpg",
        alt="Click to follow Tom's Hardware", context="Follow Tom's Hardware on Google",
    )
    assert _hard_reject(item)


def test_prompt_is_professional_science_pop_and_telegram_only():
    prompt = build_rewrite_prompt(_channel(), _row())
    assert "science-and-technology journalist" in prompt
    assert "HARD LIMIT: 900" in prompt
    assert "Telegraph" not in prompt
    assert "2-4 short paragraphs" in prompt
    assert "NO HEADLINE" in prompt
    assert "one clear idea per sentence" in prompt


def test_final_post_has_hard_900_character_limit(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    good = """ТЕКСТ: Uber Eats і Zipline планують запустити доставку їжі дронами в районі Даллас-Форт-Ворт пізніше цього року. Партнери хочуть масштабувати сервіс і до 2029 року вийти на мільйон доставок на день.

Для Uber це спосіб автоматизувати «останню милю». Для Zipline — розширити використання автономних систем доставки у США."""
    parsed = validate_rewrite(good, allowed_years={2025, 2026, 2029})
    assert len(parsed["post"]) <= POST_HARD_LIMIT
    assert "Читати повністю" not in parsed["post"]
    assert "telegra.ph" not in parsed["post"]
    assert not parsed["headline"]
    assert not parsed["post"].startswith("Uber і Zipline готують")
    with pytest.raises(TelegramError):
        build_post_text("А" * 901)


def test_invented_number_is_rejected(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    bad = """ТЕКСТ: Компанія представила нову систему для дата-центрів. Вона працює зі швидкістю 900 Гбіт/с і має зменшити затримки у великих ШІ-кластерах.

Розробники кажуть, що рішення орієнтоване на високонавантажені обчислення та повинно спростити масштабування мережевої інфраструктури."""
    with pytest.raises(Exception, match="число"):
        validate_rewrite(bad, allowed_numbers={"800"})


def test_media_and_text_only_posts_have_different_hard_limits(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    media_prompt = build_rewrite_prompt(_channel(), _row(), hard_limit=MEDIA_POST_HARD_LIMIT)
    text_prompt = build_rewrite_prompt(_channel(), _row(), hard_limit=TEXT_POST_HARD_LIMIT)
    assert "HARD LIMIT: 900" in media_prompt
    assert "HARD LIMIT: 4096" in text_prompt
    assert "1800-3400" in text_prompt

    para = ("Це завершене речення про технологічну подію та її значення для користувачів. " * 8).strip()
    long_body = para + "\n\n" + para + "\n\n" + para
    raw = "ТЕКСТ: " + long_body
    parsed = validate_rewrite(raw, hard_limit=TEXT_POST_HARD_LIMIT)
    assert 900 < len(parsed["post"]) <= TEXT_POST_HARD_LIMIT
    with pytest.raises(Exception, match="900"):
        validate_rewrite(raw, hard_limit=MEDIA_POST_HARD_LIMIT)


def test_incomplete_ai_output_is_rejected_instead_of_published(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    broken = """ТЕКСТ: У відео Apple показала прототип навушників із камерою. Система має допомагати Siri аналізувати довкілля.

Користувач у демонстрації просить асистента запам’ятати книгу, після чого функція Visual Intelligence"""
    with pytest.raises(Exception, match="обірвав"):
        validate_rewrite(broken, hard_limit=MEDIA_POST_HARD_LIMIT)


def test_service_selects_limit_from_real_media_state():
    source = inspect.getsource(AutopilotService._process)
    assert "MEDIA_POST_HARD_LIMIT if hero is not None else TEXT_POST_HARD_LIMIT" in source
    assert "hard_limit=telegram_hard_limit" in source
    assert "hard_limit=rewrite_hard_limit" in source


def test_dense_single_paragraph_is_rejected(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    dense = "ТЕКСТ: " + ("Це коротке речення про систему спостереження та її роботу. " * 10)
    with pytest.raises(Exception, match="стін.*тексту"):
        validate_rewrite(dense, hard_limit=MEDIA_POST_HARD_LIMIT)


def test_overloaded_sentence_is_rejected(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    long_sentence = " ".join(["система"] * 35) + "."
    raw = "ТЕКСТ: Коротке вступне речення про технологію.\n\n" + long_sentence
    with pytest.raises(Exception, match="34 слів"):
        validate_rewrite(raw, hard_limit=MEDIA_POST_HARD_LIMIT)


def test_body_only_builder_does_not_add_headline():
    text = "Перший абзац завершується нормально.\n\nДругий абзац також завершується нормально."
    assert build_post_text(text) == text
    assert build_post_text("\u200b", text) == text
