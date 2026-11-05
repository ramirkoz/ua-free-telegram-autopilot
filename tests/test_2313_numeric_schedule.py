"""2.3.13 regression: 05 Nov #91334 outage schedule numeric QA.

The original source has fused Telegram schedule rows; validating real times
must not make invented/malformed hours legal. No historical Telegram replay.
"""
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.editorial import _number_tokens, validate_writer_output
from telegram_autopilot.v2.numeric_schedule_2313 import (
    restore_joined_schedule_rows, schedule_guidance, numeric_atoms,
)

SOURCE_91334 = (
    "У Запоріжжі 5 листопада оновили графік відключень світла. "
    "У графіках змінили час відключення груп 1.2 та 5.1. "
    "Актуальний графік:1.1: 00:00 – 05:00, 09:00 – 14:00, 18:00 – 22:30"
    "1.2: 00:00 – 00:30, 13:30 – 17:00, 21:00 – 24:00"
    "2.1: 01:30 – 06:30, 10:30 – 15:30, 19:30 – 24:00"
    "2.2: 04:30 – 09:30, 13:30 – 18:30"
    "3.1: 00:00 – 05:00, 09:00 – 14:00, 18:00 – 22:30"
    "3.2: 00:00 – 02:00, 07:30 – 10:00, 16:30 – 21:30"
    "4.1: 06:00 – 11:00, 15:00 – 20:00"
    "4.2: 06:00 – 11:00, 15:00 – 20:00"
    "5.1: 00:00 – 00:30, 13:30 – 17:00, 21:00 – 24:00"
    "5.2: 04:30 – 09:30, 13:30 – 18:30"
)


def article(raw=SOURCE_91334):
    return SimpleNamespace(
        raw_text=raw, title="У Запоріжжі оновили графік світла 5 листопада",
        source_name="Джерело", source_url="https://t.me/zaborzp/157311",
    )


def test_91334_schedule_rows_are_split_without_changing_any_clock_value():
    cleaned = restore_joined_schedule_rows(SOURCE_91334)
    assert "22:30\n1.2:" in cleaned
    assert "24:00\n2.1:" in cleaned
    assert "21:30\n4.1:" in cleaned
    assert "20:00\n5.1:" in cleaned
    assert "21:3041" not in cleaned


def test_atomic_numbers_do_not_merge_whole_schedule_into_one_token():
    source = _number_tokens(SOURCE_91334)
    assert {"5", "1.1", "1.2", "2.1", "21:30", "22:30", "24:00", "00:00"} <= source
    assert "22:301.2" not in source
    assert "21:3041" not in source
    assert numeric_atoms("3 500 грн і 2026 рік") == {"3500", "2026"}


def test_real_times_pass_numeric_guard_and_invented_or_malformed_times_fail():
    src = _number_tokens(SOURCE_91334)
    valid = "У Запоріжжі графік для черги 1.2 діє з 13:30 до 17:00. Для черги 3.2 зазначено 21:30."
    assert not _number_tokens(valid) - src
    for bad in (
        valid.replace("13:30", "13:31"),
        valid.replace("21:30", "21:3041"),
        valid.replace("17:00", "24:006"),
        valid.replace("17:00", "42:06:00"),
    ):
        assert _number_tokens(bad) - src


def test_numeric_guard_survives_real_writer_validation():
    good = (
        "У Запоріжжі оновили графік відключень світла на 5 листопада. "
        "Для черги 1.2 зазначено відключення з 13:30 до 17:00, "
        "а для черги 3.2 — до 21:30."
    )
    assert validate_writer_output(article(), good, min_chars=80, max_chars=750)
    bad = good.replace("13:30", "13:31")
    with pytest.raises(ValueError, match="AI додав число"):
        validate_writer_output(article(), bad, min_chars=80, max_chars=750)


def test_glued_day_month_and_model_identifiers_still_protected():
    assert "22" in _number_tokens("транспорту22 жовтня")
    assert "22" not in _number_tokens("GPT22 та iPhone22")
    assert _number_tokens("Нова дата 23 жовтня") - _number_tokens("Діє 22 жовтня")


def test_schedule_guidance_only_on_time_rich_source():
    assert "Не вигадуй часових проміжків" in schedule_guidance(SOURCE_91334)
    assert not schedule_guidance("У Запоріжжі сьогодні 12:00 відкрили центр.")
    assert restore_joined_schedule_rows("00:00 01:30; 20:00") == "00:00 01:30; 20:00"
    assert restore_joined_schedule_rows("21:3041") == "21:3041"
