"""2.2.20 regression: exact operator original-source cases from SQLite."""
from __future__ import annotations
import pytest
from telegram_autopilot.ukrainian_quality import final_language_blockers
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.editorial import (
    deterministic_monitoring_exclusion, hard_editorial_reject, prepublish_quality_issues,
)

GLOSSARY = (
    "Кібергігієна – це базові правила безпечноїповедінки в цифровому просторі, "
    "якідопомагають кожній людині захиститиособисті та робочі пристрої, "
    "а такожособисті дані."
)
GOOD_DRAFT = "Надпровідний чип аналізує дані плазми з токамака й може прогнозувати зриви."
BAD_FINAL = (
    "Надпровідний чип обробляє дані плазми зі швидкістю мільйон зразків "
    "на секунду, щоб ловити передзвіри зриви в токамаках. "
    "Такі зриви можуть пошкодити реактор."
)


def channel(enabled=True, mode=ChannelMode.MONITORING):
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1000",
        mode=mode, policy=ChannelPolicy(
            channel_id=3,
            rejection_rules="[LIVE_NOW_RC96] local monitoring" if enabled else "",
        ),
    )


def article(text):
    return {
        "id":74332, "channel_id":3, "source_id":159, "title":text,
        "raw_text":text, "source_url":"https://t.me/mih_gromada/4653",
    }


def test_nonsense_introduced_by_second_editor_is_never_valid():
    assert "передзвіри" in str(final_language_blockers(BAD_FINAL))
    assert not final_language_blockers(GOOD_DRAFT)
    assert not final_language_blockers("Це допомагає передбачати зриви плазми.")
    errors = prepublish_quality_issues(
        channel(mode=ChannelMode.EDITORIAL),
        {"id":74292,"channel_id":1,"source_id":66,
         "title":"New superconducting chip aims to help tame fusion plasma",
         "raw_text":"Chip predicts tokamak disruptions.",
         "source_url":"https://example.org/fusion"},
        BAD_FINAL,
    )
    assert any("передзвіри" in item for item in errors)


def test_glossary_only_poster_blocked_before_ai_and_before_telegram():
    item=article(GLOSSARY)
    code="MONITORING_GLOSSARY_NO_EVENT"
    ch=channel()
    assert code in civic_relevance_exclusion(ch,item)
    assert code in live_now_exclusion(ch,item)
    assert code in deterministic_monitoring_exclusion(ch,item)
    assert code in hard_editorial_reject(ch,item,"Кібергігієна — це базові правила безпеки.")
    assert any(code in reason for reason in prepublish_quality_issues(
        ch,item,"Кібергігієна — це базові правила безпеки."
    ))


@pytest.mark.parametrize("good",[
    "Кібергігієна — це правила безпеки. У Михайлівській громаді провели тренінг для дітей 22 жовтня.",
    "Кібергігієна — це правила безпеки. Перевірте адресу сайту та увімкніть двофакторну автентифікацію.",
    "Кібергігієна — це правила безпеки. Телефонуйте 12345 або пишіть на info@example.ua.",
    "Кібергігієна — це правила безпеки. Докладна інструкція: https://cert.gov.ua.",
    "У Запоріжжі відкрили новий центр цифрової підтримки мешканців.",
])
def test_actual_news_and_actionable_guidance_not_suppressed(good):
    assert civic_relevance_exclusion(channel(),article(good)) == ""


def test_other_modes_and_opt_out_unchanged():
    assert civic_relevance_exclusion(channel(enabled=False),article(GLOSSARY)) == ""
    assert civic_relevance_exclusion(channel(mode=ChannelMode.EDITORIAL),article(GLOSSARY)) == ""
