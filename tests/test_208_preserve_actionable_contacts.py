from __future__ import annotations

import pytest

from telegram_autopilot.v2 import editorial


def test_208_preserve_reader_contact_when_body_near_limit():
    article = {"title": "Соціальна допомога", "raw_text": "Заяви: help@community.example", "source_name": "Громада"}
    generated = "У громаді відкрито прийом звернень від мешканців. " * 16
    result = editorial.restore_practical_literals(article, generated, hard_max_chars=750)
    assert len(result) <= 750
    assert result.endswith("Email: help@community.example")
    assert "У громаді" in result


def test_208_contact_payload_too_large_fails_closed(monkeypatch):
    article = {"raw_text": "", "source_name": "Громада"}
    monkeypatch.setattr(editorial, "_practical_literals", lambda article: [
        ("Деталі/реєстрація", "https://example.test/" + ("x" * 690)),
    ])
    with pytest.raises(ValueError, match="не вміщуються"):
        editorial.restore_practical_literals(article, "Короткий текст. " * 28, hard_max_chars=750)


def test_208_within_limit_unchanged():
    article = {"raw_text": "Контакт: care@community.example", "source_name": "Громада"}
    result = editorial.restore_practical_literals(article, "Напишіть для участі.", hard_max_chars=750)
    assert result == "Напишіть для участі.\n\nEmail: care@community.example"
