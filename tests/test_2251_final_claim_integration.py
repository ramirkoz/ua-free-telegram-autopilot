"""2.2.51 integration: same-source FINAL guard and publication-language hard floor."""
import inspect

from telegram_autopilot.v2.editorial import EditorialEngine, prepublish_quality_issues
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy


def test_writer_and_final_editor_share_semantic_contract_without_new_ai_stage():
    writer = inspect.getsource(EditorialEngine.write)
    editor = inspect.getsource(EditorialEngine._final_edit)
    assert "FINAL_CLAIM_REVIEW_RULE" in writer
    assert "FINAL_CLAIM_REVIEW_RULE" in editor
    assert "draft_final_regressions(draft, candidate)" in editor
    assert "draft_final_regressions(draft, final)" in writer
    assert "FINAL_EDIT_CLAIM_DELTA_QA" in writer
    assert "FINAL_EDIT_CLAIM_DELTA_QA" in editor
    assert 'purpose="final_editor"' in editor
    assert "validate_writer_output(" in editor


def test_older_ready_text_is_language_checked_on_all_channels():
    article = {
        "id": 88888, "channel_id": 1, "source_id": 51,
        "title": "Планетна система",
        "raw_text": "Дослідники описали планетну систему. Спостереження дозволяють оцінити її майбутнє.",
        "source_url": "https://example.org/science",
        "canonical_source_url": "https://example.org/science",
    }
    text = (
        "Астрономи описали нову планетну систему та її розвиток. "
        "Дані допомагають уявити майбутнє нашої власної планетні системи."
    )
    for channel_id, mode in [(1, ChannelMode.EDITORIAL), (2, ChannelMode.EDITORIAL),
                             (3, ChannelMode.MONITORING)]:
        channel = ChannelConfig(
            id=channel_id, name="QA", telegram_chat_id="@test",
            mode=mode, policy=ChannelPolicy(channel_id=channel_id),
        )
        issues = prepublish_quality_issues(channel, article, text)
        assert any("UK_CASE" in item for item in issues)
