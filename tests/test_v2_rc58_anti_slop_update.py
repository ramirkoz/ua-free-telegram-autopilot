from __future__ import annotations

import json

from telegram_autopilot.anti_slop import assess_ukrainian_slop, sanitize_text
from telegram_autopilot.v2.update_protocol import UpdateProtocol


def test_rc58_anti_slop_rejects_canned_ai_prose() -> None:
    text = (
        "Варто зазначити, що це важливий крок. Таким чином, технологія відкриває нові можливості. "
        "Головна перевага полягає в тому, що це дозволяє працювати швидше. "
        "Це не просто оновлення, а новий рівень для користувачів."
    )
    result = assess_ukrainian_slop(text, profile="news")
    assert not result.publishable
    assert result.score < result.gate


def test_rc58_anti_slop_accepts_plain_news_copy() -> None:
    text = (
        "Дослідники зібрали прототип батареї, який працює за нижчої температури. "
        "У випробуванні елемент зберіг більшу частину ємності після циклів заряджання. "
        "Команда планує перевірити конструкцію на більшій серії зразків."
    )
    result = assess_ukrainian_slop(text, profile="news")
    assert result.publishable
    assert result.score >= result.gate


def test_rc58_sanitizer_removes_hidden_controls() -> None:
    assert sanitize_text("тест\u200b текст\ufeff") == "тест текст"


def test_rc58_update_request_accepts_utf8_bom(tmp_path) -> None:
    protocol = UpdateProtocol(tmp_path / "updates")
    path = tmp_path / "request.json"
    payload = {
        "request_id": "rc58-bom-test",
        "target_version": "2.0.0-rc58",
        "sha256": "a" * 64,
        "created_at": "2026-09-18T17:00:00+03:00",
        "source": "test",
    }
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    request = protocol.load_request(path)
    assert request is not None
    assert request.target_version == "2.0.0-rc58"
    assert request.request_id == "rc58-bom-test"
