"""2.2.45 Ukrainian grammar QA from 27 Oct operator screenshot.

A coherent sentence must be source-grounded. Fail closed on high-confidence
agreement mistakes without blindly "correcting" meaning or changing source
attribution. Regression applies to all three channels and late READY legacy.
"""
import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import prepublish_quality_issues, validate_writer_output
from telegram_autopilot.v2.ukrainian_agreement_245 import (
    POST_TRANSLATION_WRITER_RULE, POST_TRANSLATION_FINAL_RULE,
    high_confidence_agreement_issues,
)


BAD = (
    "Поліція США дедалі частіше зупиняє водіїв за підозрою, "
    "який висуває штучний інтелект. Згідно зі звітом ACLU, алгоритми "
    "аналізують історію переміщень і позначають деякі маршрути як підозрілі "
    "навіть без доказів злочину."
)
GOOD = (
    "Поліція США дедалі частіше зупиняє водіїв через підозри, "
    "сформовані системами штучного інтелекту. Згідно зі звітом ACLU, "
    "алгоритми аналізують історію переміщень і позначають деякі маршрути "
    "як підозрілі навіть без доказів злочину."
)
SOURCE = (
    "US police increasingly stop drivers based on suspicion from artificial "
    "intelligence. According to ACLU, license plate recognition networks "
    "track movement histories and flag routes without evidence of a crime."
)


@pytest.mark.parametrize("noun", ["підозрою", "підозру", "системою", "компанією", "програмою", "моделлю"])
@pytest.mark.parametrize("relative", ["який", "яке", "котрий", "котре"])
def test_high_confidence_gender_agreement_mismatch(noun, relative):
    result = high_confidence_agreement_issues(f"Звернулися до {noun}, {relative} може змінити ситуацію.")
    assert result and result[0].startswith("UK_RELATIVE_AGREEMENT:")


@pytest.mark.parametrize("copy", [
    GOOD,
    "Компанія представила програму, яка допомагає планувати витрати.",
    "У компанії, яка працює у Львові, відкрили новий офіс.",
    "Система, яку встановили у школі, працює.",
    "Згідно із звітом ACLU, поліція застосовує автоматичний аналіз.",
    "Він працював з компанією, яку заснували у 2020 році.",
    "Який результат отримали дослідники, поки невідомо.",
])
def test_valid_ukrainian_not_rejected(copy):
    assert high_confidence_agreement_issues(copy) == ()


def test_no_silent_regex_autocorrection():
    assert "підозрою, який" in BAD
    assert high_confidence_agreement_issues(BAD)
    assert "підозрою, який" not in GOOD
    assert not high_confidence_agreement_issues(GOOD)


@pytest.mark.parametrize("mode", [ChannelMode.EDITORIAL, ChannelMode.MONITORING])
@pytest.mark.parametrize("channel_id", [1, 2, 3])
def test_pretelegram_legacy_ready_blocked_in_every_channel(channel_id, mode):
    ch = ChannelConfig(
        id=channel_id, name=f"Test {channel_id}", telegram_chat_id="-1000",
        mode=mode, policy=ChannelPolicy(channel_id=channel_id),
    )
    article = {
        "id": 84555, "channel_id": channel_id, "source_id": 111,
        "title": "US AI-based police traffic stops", "raw_text": SOURCE,
        "source_url": "https://example.org/ai-police",
        "canonical_source_url": "https://example.org/ai-police",
    }
    issues = prepublish_quality_issues(ch, article, BAD)
    assert any("UK_TRANSLATION_AGREEMENT_QA" in issue for issue in issues)


def test_writer_validation_rejects_before_draft_can_become_ready():
    source = {
        "id": 84555, "channel_id": 1, "source_id": 111,
        "title": "AI-based traffic suspicion", "raw_text": SOURCE,
        "source_url": "https://example.org/story",
    }
    with pytest.raises(ValueError, match="UK_TRANSLATION_AGREEMENT_QA"):
        validate_writer_output(source, BAD, min_chars=120, max_chars=900)


def test_writing_and_final_editor_prompts_keep_facts_and_grammar():
    assert "відмінок" in POST_TRANSLATION_WRITER_RULE
    assert "підозрою, який" in POST_TRANSLATION_FINAL_RULE
    assert "Не дода" in POST_TRANSLATION_FINAL_RULE
    assert "SOURCE" in POST_TRANSLATION_WRITER_RULE
