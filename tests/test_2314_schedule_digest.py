"""2.3.14: preserve factual guards while avoiding padded power notices."""
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.editorial import _monitoring_limits, validate_writer_output
from telegram_autopilot.v2.editorial_hard_floor import two_sentence_reason
from telegram_autopilot.v2.schedule_digest_2314 import (
    is_change_digest_2314, schedule_digest_limits_2314,
    schedule_digest_instruction_2314,
)
from telegram_autopilot.v2.editorial_feedback_2312 import SCIENCE

# Real #91375 scenario, with synthetic minimal wording but source-owned times.
SOURCE = (
    "У Запоріжжі оновили графік відключень світла на сьогодні. "
    "Для черг 1.2 та 5.1 відключення перенесли на годину пізніше. "
    "Черги 1.2 та 5.1: 13:30–17:00 → 14:30–17:00. "
    "Для черги 3.2 зазначено 16:30–21:30. "
    "Актуальний графік: 1.1: 00:00–05:00; 1.2: 14:30–17:00, 21:00–24:00; "
    "3.2: 07:30–10:00, 16:30–21:30; 5.1: 14:30–17:00. "
    "До повного розкладу належать й інші черги з різними проміжками. "
    + "Актуальні години наведено в джерелі. " * 20
)


def article(raw=SOURCE):
    return SimpleNamespace(
        raw_text=raw, title="Графік відключень у Запоріжжі",
        source_name="Місцева новина", source_url="https://t.me/zaborzp/157313",
    )


def channel():
    return SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(target_min_chars=500,target_max_chars=750),
    )


def test_real_change_notice_gets_compact_target_without_changing_source():
    assert is_change_digest_2314(SOURCE)
    assert schedule_digest_limits_2314(SOURCE, 500, 750) == (220, 520)
    assert _monitoring_limits(channel(), article(), 750) == (220, 520, 520)
    assert "два або три" in schedule_digest_instruction_2314(SOURCE)
    assert "21:00" in SOURCE


def test_bare_schedule_and_unrelated_story_do_not_change_targets():
    only_table = "Оновлені графіки відключень: 1.1: 00:00–05:00; 1.2: 14:30–17:00; 3.2: 16:30–21:30; 5.1: 14:30–17:00."
    assert not is_change_digest_2314(only_table)
    assert schedule_digest_limits_2314(only_table, 500, 750) == (500, 750)
    assert two_sentence_reason(article(only_table)) is not None
    assert schedule_digest_limits_2314("Сьогодні відкрили новий центр.", 500, 750) == (500, 750)


def test_factual_short_post_passes_but_invented_time_is_still_rejected():
    good = (
        "У Запоріжжі оновили графік відключень світла на сьогодні. "
        "Для черг 1.2 та 5.1 відключення перенесли на годину пізніше: "
        "з 13:30 до 14:30. Повний графік містить час для інших черг."
    )
    assert 140 <= len(good) <= 520
    assert validate_writer_output(article(), good, min_chars=220,max_chars=520,hard_max_chars=520)
    with pytest.raises(ValueError,match="AI додав число"):
        validate_writer_output(article(),good.replace("14:30","14:31"),min_chars=220,max_chars=520,hard_max_chars=520)
    with pytest.raises(ValueError,match="AI додав число"):
        validate_writer_output(article(),good.replace("14:30","21:3041"),min_chars=220,max_chars=520,hard_max_chars=520)


def test_science_human_labels_prompt_now_distinguishes_corporate_forecasts():
    text=SCIENCE
    assert "майбутні потужності корпоративних дата-центрів" in text
    assert "нового перевіреного" in text
