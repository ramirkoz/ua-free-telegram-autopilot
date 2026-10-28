"""2.2.48: real Ukrainian subject/agreement and scientific certainty regressions."""
from __future__ import annotations

import pytest
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import prepublish_quality_issues
from telegram_autopilot.v2.ukrainian_agreement_245 import (
    high_confidence_agreement_issues,
    POST_TRANSLATION_WRITER_RULE,
    POST_TRANSLATION_FINAL_RULE,
)

@pytest.mark.parametrize("bad", [
    "Комети мав би зберегти органічні речовини.",
    "Молекули показала новий результат.",
    "Дослідники виявила ці сполуки.",
    "Комета мав би рухатися повільніше.",
    "Система показав результати.",
    "Програма зазначив про зміни.",
    "Кислота зберігся після удару.",
    "Дослідження показала інші дані.",
    "Зіткнення був надто швидким.",
    "Джерело підтвердив зміну.",
])
def test_high_confidence_subject_agreement_bad(bad):
    issues = high_confidence_agreement_issues(bad)
    assert any("UK_SUBJECT_" in item for item in issues)


@pytest.mark.parametrize("good", [
    "Комета мала б рухатися повільніше.",
    "Комети мали б рухатися повільніше.",
    "Молекули збереглися за низької швидкості.",
    "Система показала результати.",
    "Кислота збереглася після удару.",
    "Дослідження показало інші дані.",
    "Згідно зі звітом, зміни відбулися у 2026 році.",
    "Вчені виявили речовину, яка може утворювати складніші молекули.",
    "Дослідники зазначили, що після зіткнення могли зберегтися сполуки.",
])
def test_good_agreement_not_changed_or_blocked(good):
    assert high_confidence_agreement_issues(good) == ()


@pytest.mark.parametrize("channel_id,mode", [
    (1, ChannelMode.EDITORIAL),
    (2, ChannelMode.EDITORIAL),
    (3, ChannelMode.MONITORING),
])
def test_all_channels_block_old_ready_with_wrong_subject_verb(channel_id, mode):
    channel = ChannelConfig(
        id=channel_id, name=f"Channel {channel_id}", telegram_chat_id="@test",
        mode=mode, policy=ChannelPolicy(channel_id=channel_id),
    )
    article = {
        "id": 88001, "channel_id": channel_id, "source_id": 77,
        "title": "Comet collision model", "raw_text":
        "Researchers modeled comet impacts. They found that molecules could survive only "
        "if the comet arrived slowly. The result does not rule out asteroid sources.",
        "source_url": "https://example.org/comets",
        "canonical_source_url": "https://example.org/comets",
    }
    bad = (
        "Комета мав би рухатися повільніше, щоб зберегти молекули. "
        "Дослідники змоделювали зіткнення та описали умови збереження "
        "органічних сполук на ранній Землі."
    )
    issues = prepublish_quality_issues(channel, article, bad)
    assert any("UK_SUBJECT_GENDER" in item for item in issues)


def test_prompt_requires_scientific_uncertainty_and_factual_source():
    assert "моделювання" in POST_TRANSLATION_WRITER_RULE
    assert "гіпотезу" in POST_TRANSLATION_WRITER_RULE
    assert "ймовірно" in POST_TRANSLATION_FINAL_RULE
    assert "SOURCE" in POST_TRANSLATION_WRITER_RULE
