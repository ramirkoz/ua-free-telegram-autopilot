import pytest
from telegram_autopilot.v2.editorial import _trim_candidate_to_hard_limit

def test_trim_keeps_complete_sentence():
    text = 'Це вже підтверджена подія. ' + 'Наступна частина ' * 30
    assert _trim_candidate_to_hard_limit(text, 90, min_chars=50).endswith('.')

def test_trim_rejects_fragment_without_sentence_end():
    with pytest.raises(ValueError, match='немає завершеного речення'):
        _trim_candidate_to_hard_limit('Дослідники повідомили ' * 25, 100, min_chars=50)
