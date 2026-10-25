"""2.2.32 regression: ironic Telegram commentary cannot turn into asserted news."""
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.monitoring_editorial_stance_232 import (
    monitoring_editorial_question_reason,
    monitoring_source_stance_reason,
    monitoring_unattributed_sarcasm_reason,
    monitoring_unattributed_editorial_money_reason,
)
from telegram_autopilot.v2.source_fact_integrity import non_overridable_quality_issues


SOURCE = (
    "Мунварта склала 41 протокол за тиждень — оце так робота "
    "за понад 16 млн грн/рік. Дууууже важливе \"підприємство\" для міста.\n\n"
    "З Космічного на правий перемикнулись, бо на Космосі "
    "некомфортно стало працювати?"
)
BAD_OUTPUT = (
    "Мунварта склала 41 протокол за тиждень — оце так виглядає "
    "робота за понад 16 млн грн на рік. "
    "Працівники з Космічного району перейшли на правий берег, "
    "бо на Космосі стало некомфортно працювати."
)
GOOD_OUTPUT = (
    "За тиждень муніципальна варта склала 41 адміністративний протокол. "
    "Цю цифру наводить повідомлення «Запоріжжя.ІНФО»."
)


def article(raw=SOURCE):
    return {
        "id": 90001,
        "title": "Мунварта за тиждень склала 41 протокол",
        "raw_text": raw,
        "source_name": "ЗАПОРІЖЖЯ.ІНФО",
        "source_url": "https://t.me/example/123",
    }


def channel():
    return SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(
            rejection_rules="[LIVE_NOW_RC96]",
            monitoring_denied_origins="",
            monitoring_source_policy="institutional",
        ),
    )


def test_operator_failure_question_cannot_become_assertive_fact():
    assert monitoring_editorial_question_reason(article(), BAD_OUTPUT) == (
        "MONITORING_EDITORIAL_QUESTION_AS_FACT"
    )


def test_operator_failure_cannot_adopt_source_sarcastic_narrator():
    assert monitoring_unattributed_sarcasm_reason(article(), BAD_OUTPUT) == (
        "MONITORING_SOURCE_SARCASM_ADOPTED"
    )


def test_plain_factual_report_from_same_original_remains_eligible():
    assert monitoring_source_stance_reason(article(), GOOD_OUTPUT) == ""


def test_report_of_original_editorial_question_is_allowed_when_attributed():
    text = (
        "Мунварта склала 41 протокол. "
        "Редакція запитує, чи перейшли працівники з Космічного району "
        "на правий берег, бо на Космосі стало некомфортно працювати."
    )
    assert monitoring_editorial_question_reason(article(), text) == ""


def test_question_kept_as_question_not_upgraded():
    assert monitoring_editorial_question_reason(
        article(), "З Космічного на правий перейшли, бо некомфортно працювати?"
    ) == ""


def test_no_false_positive_when_source_has_independent_affirmative_statement():
    source = (
        "У Запоріжжі відкрили муніципальний центр підтримки родин. "
        "Чи відкрили у Запоріжжі муніципальний центр підтримки родин?"
    )
    out = "У Запоріжжі відкрили муніципальний центр підтримки родин."
    assert monitoring_editorial_question_reason(article(source), out) == ""


def test_irony_in_original_does_not_force_rejection_of_clean_source_facts():
    source = (
        "У Запоріжжі відкрили муніципальний центр підтримки родин. "
        "Оце так, цікаво, скільки мільйонів на це витратили?"
    )
    out = "У Запоріжжі відкрили муніципальний центр підтримки родин."
    assert monitoring_source_stance_reason(article(source), out) == ""


def test_distinct_unrelated_question_does_not_block_other_city_news():
    source = (
        "У Запоріжжі відкрили центр допомоги мешканцям. "
        "Коли полагодять стару автобусну зупинку?"
    )
    out = "У Запоріжжі відкрили центр допомоги мешканцям."
    assert monitoring_editorial_question_reason(article(source), out) == ""


@pytest.mark.parametrize("unsafe", [
    BAD_OUTPUT,
    ("Мунварта склала 41 протокол за тиждень. "
     "Працівники з Космічного району перейшли на правий берег, "
     "бо на Космосі стало некомфортно працювати."),
])
def test_no_model_or_human_approval_can_bypass_source_stance(unsafe):
    assert hard_editorial_reject(channel(), article(), unsafe) in {
        "MONITORING_EDITORIAL_QUESTION_AS_FACT",
        "MONITORING_SOURCE_SARCASM_ADOPTED",
    }
    assert "MONITORING_EDITORIAL_QUESTION_AS_FACT" in (
        non_overridable_quality_issues(channel(), article(), unsafe)
    )


def test_guard_is_monitoring_only_not_commercial_editorial():
    editorial_channel = SimpleNamespace(mode=ChannelMode.EDITORIAL)
    assert "MONITORING_EDITORIAL_QUESTION_AS_FACT" not in (
        non_overridable_quality_issues(editorial_channel, article(), BAD_OUTPUT)
    )


def test_exact_plain_numerical_fact_does_not_trigger_stance_guard():
    assert monitoring_source_stance_reason(
        article(), "Мунварта склала 41 адміністративний протокол за тиждень."
    ) == ""


def test_opinionated_source_budget_is_not_independently_verified():
    clean_but_unverified = (
        "Мунварта склала 41 протокол за тиждень. "
        "Робота муніципальної варти коштує понад 16 млн грн на рік."
    )
    assert monitoring_unattributed_editorial_money_reason(
        article(), clean_but_unverified
    ) == "MONITORING_SOURCE_EDITORIAL_MONEY_AS_FACT"


def test_source_budget_commentary_remains_attributed_as_claim():
    attributed = (
        "Мунварта склала 41 протокол. "
        "Редакція пише про понад 16 млн грн на рік, "
        "але ця цифра не підтверджена наведеним документом."
    )
    assert monitoring_unattributed_editorial_money_reason(article(), attributed) == ""


def test_independent_nonsarcastic_source_budget_statement_is_not_blocked():
    raw = (
        "За затвердженим бюджетом на утримання варти передбачено 16 млн грн. "
        + SOURCE
    )
    final = "На утримання муніципальної варти передбачено 16 млн грн на рік."
    assert monitoring_unattributed_editorial_money_reason(article(raw), final) == ""
