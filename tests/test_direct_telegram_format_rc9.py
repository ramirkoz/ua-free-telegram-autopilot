from __future__ import annotations

import inspect
import sqlite3

import pytest

from telegram_autopilot.media_pipeline import PreparedMedia, _hard_reject
from telegram_autopilot.models import Channel
from telegram_autopilot.production_pipeline_rc9 import POST_HARD_LIMIT, build_rewrite_prompt, validate_rewrite
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
    assert "2-4 compact paragraphs" in prompt


def test_final_post_has_hard_900_character_limit(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    good = """ЗАГОЛОВОК: Uber і Zipline готують доставку їжі дронами
ТЕКСТ: Uber Eats і Zipline планують запустити доставку їжі дронами в районі Даллас-Форт-Ворт пізніше цього року. Партнери хочуть масштабувати сервіс і до 2029 року вийти на мільйон доставок на день. Для Uber це спосіб автоматизувати «останню милю», а для Zipline — розширити використання автономних систем доставки у США."""
    parsed = validate_rewrite(good, allowed_years={2025, 2026, 2029})
    assert len(parsed["post"]) <= POST_HARD_LIMIT
    assert "Читати повністю" not in parsed["post"]
    assert "telegra.ph" not in parsed["post"]
    with pytest.raises(TelegramError):
        build_post_text("Короткий заголовок", "А" * 900)


def test_invented_number_is_rejected(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    bad = """ЗАГОЛОВОК: Нова система прискорює обмін даними
ТЕКСТ: Компанія представила нову систему для дата-центрів. Вона працює зі швидкістю 900 Гбіт/с і має зменшити затримки у великих ШІ-кластерах. Розробники кажуть, що рішення орієнтоване на високонавантажені обчислення та повинно спростити масштабування мережевої інфраструктури."""
    with pytest.raises(Exception, match="число"):
        validate_rewrite(bad, allowed_numbers={"800"})
