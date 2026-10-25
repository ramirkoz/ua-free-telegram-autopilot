"""2.2.30 regression: original-source voice, local effect and leaked AI scaffolding."""
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.editorial import (
    _EDITORIAL_META_LEAK_RE,
    hard_editorial_reject,
)
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_source_voice_230 import (
    original_global_commentary_reason,
    source_voice_output_reason,
)


def monitoring():
    return SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(
            rejection_rules="[LIVE_NOW_RC96]",
            monitoring_denied_origins="",
            monitoring_source_policy="institutional",
        ),
    )


TARIFF_REACTION = (
    "Я сказав, що треба встановити 200% мито для України та Росії. "
    "Я ніколи не думав про таке раніше. Ми припинили п'ять війн тарифами."
)


def test_twitter_style_quote_cannot_become_zaporizhzhia_civic_news():
    article = dict(raw_text=TARIFF_REACTION, title="200% мита?", source_name="Запоріжжя.ІНФО")
    assert original_global_commentary_reason(article) == "MONITORING_UNATTRIBUTED_GLOBAL_COMMENTARY_NOT_LOCAL"
    assert civic_relevance_exclusion(monitoring(), article) == "MONITORING_UNATTRIBUTED_GLOBAL_COMMENTARY_NOT_LOCAL"


def test_local_policy_outcome_is_not_lost_merely_because_source_quotes_first_person():
    article = dict(
        raw_text=(
            "У Запоріжжі мешканці отримали нові виплати за програмою допомоги. "
            + TARIFF_REACTION
        ),
        title="Підсумки програми",
        source_name="Міська служба",
    )
    assert original_global_commentary_reason(article) == ""


def test_unrelated_local_event_survives_source_voice_gate():
    article = dict(
        raw_text=(
            "У Запоріжжі відкрили центр допомоги мешканцям. "
            "Працівники пояснили умови звернення."
        ),
        title="Центр допомоги",
        source_name="Міська рада",
    )
    assert original_global_commentary_reason(article) == ""
    assert civic_relevance_exclusion(monitoring(), article) == ""


@pytest.mark.parametrize("output", [
    "Мовець також заявив, що про мита він раніше не думав.",
    "У заяві запропонували негайно встановити 200% мито.",
    "Неназваний представник сказав, що змін не буде.",
])
def test_first_person_quote_must_not_be_anonymous_report(output):
    assert source_voice_output_reason({"raw_text": TARIFF_REACTION}, output) == "MONITORING_SOURCE_SPEAKER_LOST"


def test_quoted_speaker_is_not_fabricated_if_named_in_rewrite():
    assert source_voice_output_reason(
        {"raw_text": TARIFF_REACTION},
        "Дональд Трамп заявив про запропоновані мита.",
    ) == ""


def test_local_publication_without_first_person_not_blocked_for_speaker_word():
    assert source_voice_output_reason(
        {"raw_text": "У Запоріжжі відбувся форум. Учасники обговорили послуги."},
        "Мовець виступив на форумі.",
    ) == ""


@pytest.mark.parametrize("heading", [
    "Текст поста:",
    "**Текст поста:**",
    "ТЕКСТ ПОСТА: Новина",
    "# Текст публікації:",
    "Готовий пост: Новина",
])
def test_meta_headings_are_blocked(heading):
    assert _EDITORIAL_META_LEAK_RE.search(heading + "\nУ Запоріжжі працює новий центр.")


def test_meta_block_precedes_any_editorial_mode_specific_checks():
    channel = SimpleNamespace(mode=ChannelMode.EDITORIAL)
    assert hard_editorial_reject(channel, {"raw_text": ""}, "**Текст поста:**\nТекст новини.") == "EDITORIAL_META_LEAK"


def test_plain_news_is_not_confused_with_meta_heading():
    text = "У Запоріжжі відкрили центр допомоги. Він працюватиме щодня."
    assert _EDITORIAL_META_LEAK_RE.search(text) is None
