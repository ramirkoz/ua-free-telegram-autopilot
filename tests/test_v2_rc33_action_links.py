from __future__ import annotations

import pytest

from telegram_autopilot.fact_guard import FactGuardError, validate_fact_guard
from telegram_autopilot.v2.strict_ingest import StrictTelegramParser, strict_stitch_telegram


def _telegram_html(body: str) -> str:
    return f"""
    <div class="tgme_widget_message" data-post="zaporizhzhia_test/12345">
      <div class="tgme_widget_message_text">{body}</div>
      <time datetime="2026-09-15T08:30:00+00:00"></time>
    </div>
    """


def test_hidden_registration_href_survives_strict_telegram_ingest() -> None:
    target = "https://forms.example.org/zaporizke-kolo?school=8-11"
    parser = StrictTelegramParser("zaporizhzhia_test")
    parser.feed(
        _telegram_html(
            'Реєстрація триває до 18 вересня (12:00) за '
            f'<a href="{target}">посиланням</a>.'
        )
    )
    parser.close()

    assert len(parser.entries) == 1
    entry = parser.entries[0]
    assert target in entry.text

    articles = strict_stitch_telegram("zaporizhzhia_test", parser.entries)
    assert len(articles) == 1
    assert target in articles[0].raw_text
    assert articles[0].url == "https://t.me/zaporizhzhia_test/12345"


def test_actionable_registration_url_is_mandatory_in_rewrite() -> None:
    target = "https://forms.example.org/apply?id=zaporizke-kolo"
    article = {
        "title": "Триває реєстрація до програми «Запорізьке коло»",
        "raw_text": f"Подати заявку можна до 18 вересня за посиланням {target}",
    }

    validate_fact_guard(
        article,
        f"Подати заявку можна до 18 вересня. Реєстрація: {target}",
    )

    with pytest.raises(FactGuardError, match="практичне посилання"):
        validate_fact_guard(
            article,
            "Подати заявку можна до 18 вересня, за посиланням у дописі.",
        )


def test_generic_source_link_is_not_forced_into_body() -> None:
    article = {
        "title": "Місто опублікувало новий аналітичний огляд",
        "raw_text": "Огляд пояснює зміни у міському просторі. https://example.org/research",
    }
    validate_fact_guard(
        article,
        "Новий огляд пояснює зміни у міському просторі та їхній контекст.",
    )


def test_source_footer_cannot_replace_distinct_action_url() -> None:
    action = "https://forms.example.org/register"
    source_post = "https://t.me/zaporizhzhia_test/12345"
    article = {
        "title": "Реєстрація на програму",
        "raw_text": f"Реєстрація учасників доступна за посиланням {action}",
    }

    with pytest.raises(FactGuardError, match="практичне посилання"):
        validate_fact_guard(
            article,
            f"Реєстрація триває. Джерело: {source_post}",
        )
