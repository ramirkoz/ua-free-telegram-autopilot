from __future__ import annotations

from types import SimpleNamespace

from telegram_autopilot import rc45_policy as rc45
from telegram_autopilot import rc69_media_language as rc69
from telegram_autopilot import rc70_mixed_language as rc70


UA_TEXT = (
    "Це український матеріал про роботу громади та нові рішення. У повідомленні пояснюють, що зміни "
    "стосуються мешканців і вже діють цього тижня. Автори додають деталі, умови та подальші кроки, "
    "щоб читачі могли зрозуміти, що саме відбулося і де шукати додаткову інформацію."
)
RU_TEXT = (
    "Это российский текст о работе города и новом решении, которое уже действует на этой неделе. "
    "В сообщении объясняют, что изменилось для жителей, какие условия нужно учитывать и где можно "
    "получить дополнительную информацию. Также указаны дальнейшие шаги и сроки выполнения решения."
)
EN_TEXT = (
    "This is an English source about a city decision that is already in effect this week. The report explains "
    "what changed for residents, which conditions apply, where people can find more information and what steps "
    "will follow next. It contains enough ordinary English prose to pass the normal English source detector."
)


def _prepare() -> None:
    rc70._PREV_ACCEPTS = rc69.accepts_input


def test_mixed_ua_ru_to_ua_accepts_both_languages() -> None:
    _prepare()
    assert rc70.accepts_input_rc70(rc70.DIRECTION_UKRU_TO_UK, UA_TEXT)
    assert rc70.accepts_input_rc70(rc70.DIRECTION_UKRU_TO_UK, RU_TEXT)


def test_mixed_ua_ru_to_ua_rejects_english_source() -> None:
    _prepare()
    assert not rc70.accepts_input_rc70(rc70.DIRECTION_UKRU_TO_UK, EN_TEXT)


def test_existing_language_modes_keep_their_original_behavior() -> None:
    _prepare()
    assert rc70.accepts_input_rc70(rc45.DIRECTION_EN_TO_UK, EN_TEXT)
    assert rc70.accepts_input_rc70(rc69.DIRECTION_UK_TO_UK, UA_TEXT)
    assert rc70.accepts_input_rc70(rc69.DIRECTION_RU_TO_UK, RU_TEXT)


def test_rc45_channel_direction_can_register_mixed_mode_without_channel_name_rule() -> None:
    old = dict(rc45.DIRECTION_LABELS)
    try:
        rc45.DIRECTION_LABELS[rc70.DIRECTION_UKRU_TO_UK] = rc70.DIRECTION_LABEL
        channel = SimpleNamespace(content_direction=rc70.DIRECTION_UKRU_TO_UK)
        assert rc45.content_direction(channel) == rc70.DIRECTION_UKRU_TO_UK
    finally:
        rc45.DIRECTION_LABELS.clear()
        rc45.DIRECTION_LABELS.update(old)


def test_mixed_source_language_is_not_persisted_as_english() -> None:
    calls = []
    rc70._PREV_UPDATE_ARTICLE = lambda db, article_id, **fields: calls.append((db, article_id, fields))
    token = rc45._CURRENT_DIRECTION.set(rc70.DIRECTION_UKRU_TO_UK)
    try:
        marker = object()
        rc70._update_article_rc70(marker, 17, language="en", status="processing")
    finally:
        rc45._CURRENT_DIRECTION.reset(token)
    assert calls[0][1] == 17
    assert calls[0][2]["language"] == "uk-ru"
