"""2.2.39 LIVE regressions: SQLite Row publication parity and QA cascade."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from telegram_autopilot.v2 import telegram_media_publish_guard as guard
from telegram_autopilot.v2.ai_gateway import _rc111_qa_signature
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.qa_adjacent_word_239 import repair_adjacent_repeated_word

QA = ValueError("Жорсткий QA: сусіднє слово повторено двічі")


def _row(records):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT ? AS article_layout_json, ? AS media_json",
        (json.dumps({"telegram": {"source_message_records_v1": records}}), "[]"),
    ).fetchone()
    assert not hasattr(row, "get")  # Production V2Store.get_article contract.
    return row


def _records(*, explicit_link):
    return [
        {"post": "community/302",
         "text": "Офіційний текст. " + ("Фото: https://t.me/community/301" if explicit_link else ""),
         "media": ["image:https://media.test/source.jpg"], "reply_to_post": "", "grouped_id": ""},
        {"post": "community/301", "text": "",
         "media": ["image:https://media.test/extra.jpg"], "reply_to_post": "", "grouped_id": ""},
    ]


def _bundle():
    return SimpleNamespace(
        count=2, source_message_ids=("302", "301"),
        encoded_items=[
            "image:https://media.test/source.jpg", "image:https://media.test/extra.jpg"
        ],
    )


def _preflight(monkeypatch):
    monkeypatch.setattr(
        guard, "check_exact_telegram_media",
        lambda _: SimpleNamespace(
            outcome="confirmed", media=["image:https://media.test/source.jpg"],
            expected_photos=1, video_expected=False,
            photo_signal="photo_wrap", video_signal="", reason="exact_post_media_confirmed"
        ),
    )
    monkeypatch.setattr(guard, "source_media_shortfall", lambda check, media: "")


def test_verified_same_channel_split_photo_row_does_not_crash(monkeypatch):
    _preflight(monkeypatch)
    row = _row(_records(explicit_link=True))
    channel = SimpleNamespace(id=3, mode=ChannelMode.MONITORING)
    assert guard._verified_split_media(row, _bundle(), "https://t.me/community/302", channel)
    outcome = guard.enforce_source_media_parity(
        SimpleNamespace(), channel, 83163, row, _bundle(), "https://t.me/community/302"
    )
    assert isinstance(outcome, tuple) and outcome[0] is row
    assert outcome[1].count == 2


def test_unlinked_neighbor_stays_blocked_even_after_sqlite_row_fix(monkeypatch):
    _preflight(monkeypatch)
    row = _row(_records(explicit_link=False))
    channel = SimpleNamespace(id=3, mode=ChannelMode.MONITORING)
    assert not guard._verified_split_media(row, _bundle(), "https://t.me/community/302", channel)
    backoffs = []
    publisher = SimpleNamespace(
        store=SimpleNamespace(
            update_article=lambda *a, **kw: None,
            publication_backoff=lambda *a, **kw: backoffs.append((a, kw))
        )
    )
    monkeypatch.setattr(guard, "build_publication_media_bundle", lambda *a, **kw: _bundle())
    result = guard.enforce_source_media_parity(
        publisher, channel, 83163, row, _bundle(), "https://t.me/community/302"
    )
    assert result == "MEDIA_CROSS_POST_CONTAMINATION"
    assert len(backoffs) == 1
    assert backoffs[0][1]["error_code"] == "MEDIA_CROSS_POST_CONTAMINATION"


def test_repeated_word_is_a_deterministic_two_route_failure_signature():
    assert _rc111_qa_signature(QA) == "repeated_word"
    assert _rc111_qa_signature(ValueError("MONITORING_SOURCE_POLARITY_FLIP")) == ""
    assert _rc111_qa_signature(ValueError("AI додав число, якого немає у джерелі")) == "invented_number"


def test_simple_duplicate_word_is_repaired_without_adding_facts():
    source = ("Сьогодні в громаді відкрили новий центр для ветеранів. "
              "Працівники працівники центру розповіли про доступні послуги для мешканців.")
    result = repair_adjacent_repeated_word(source, QA)
    assert "Працівники працівники" in source  # Capitals intentionally not auto-corrected.
    assert result == ""
    source = source.replace("Працівники працівники", "працівники працівники")
    result = repair_adjacent_repeated_word(source, QA)
    assert "працівники працівники" not in result
    assert "працівники центру" in result
    assert len(source) - len(result) == len("працівники ")


def test_no_auto_repair_for_quotes_numbers_urls_or_other_qa():
    body = ("Міська рада надала інформацію про плани розвитку. "
            "Жителі жителі зможуть звернутися до відділу.")
    assert repair_adjacent_repeated_word(body, QA) == ""
    body = body.replace("Жителі жителі", "жителі жителі")
    assert repair_adjacent_repeated_word('«' + body + '»', QA) == ""
    assert repair_adjacent_repeated_word(body + " https://t.me/community/301", QA) == ""
    assert repair_adjacent_repeated_word(body, ValueError("SOURCE_POLARITY_FLIP")) == ""
    assert repair_adjacent_repeated_word(body + " новини новини", QA) == ""
