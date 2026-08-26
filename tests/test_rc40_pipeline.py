from __future__ import annotations

import pytest

from telegram_autopilot import production_pipeline as production
from telegram_autopilot.rc40_policy import _rc40_allowed_numbers, _rc40_allowed_years, _validate_fact_guard_rc40, validate_russian_editorial_rc40
from telegram_autopilot.rewrite_verifier import assess_rewrite


def _article(**overrides):
    base = {
        "id": 40,
        "title": "A web app update arrives this week",
        "raw_text": "The company updated its web app. The change affects Email notifications and Browser sessions. The service was published on August 26.",
        "source_published_at": "2026-08-26T08:00:00Z",
        "teaser_text": "",
        "event_summary": "",
        "full_article_uk": "",
    }
    base.update(overrides)
    return base


def test_rc40_publication_year_is_allowed_temporal_metadata() -> None:
    years = _rc40_allowed_years(_article())
    assert 2026 in years
    production._validate_years("У 2026 році сервіс оновили.", years)


def test_rc40_number_guard_ignores_time_and_zero_padded_format_fragments() -> None:
    production._validate_numbers("Запуск о 09:30:00.", _rc40_allowed_numbers(_article(), "Запуск о 09:30:00."))
    production._validate_numbers("Версії 01/02 перевірено.", _rc40_allowed_numbers(_article(), "Версії 01/02 перевірено."))


def test_rc40_number_guard_still_blocks_new_factual_quantity() -> None:
    with pytest.raises(production.ProductionPipelineError, match="125"):
        production._validate_numbers("Компанія додала 125 серверів.", set())


def test_rc40_fact_guard_allows_generic_latin_tech_nouns() -> None:
    article = _article()
    out = "Email і Web лишилися частиною App, а Browser отримав новий режим."
    _validate_fact_guard_rc40(article, out)


def test_rc40_fact_guard_still_blocks_unknown_product_name() -> None:
    article = _article()
    with pytest.raises(Exception, match="futurabox"):
        _validate_fact_guard_rc40(article, "Компанія також представила FuturaBox.")


def test_rc40_ru_bridge_does_not_reject_useful_shorter_internal_draft() -> None:
    text = (
        "Это внутренняя редакторская заметка. Главное здесь не список функций, а то, что обновление меняет привычный сценарий. "
        "Источник сообщает о самом изменении и его последствиях, поэтому следующий редактор может начать с этого факта. "
        "Ничего нового от себя добавлять не нужно, а детали стоит оставить только те, без которых история теряет смысл."
    )
    assert len(text) < 700
    assert validate_russian_editorial_rc40(text, allowed_years=set(), allowed_numbers=set()) == text


def test_rc40_quality_77_is_soft_not_unusable() -> None:
    body = (
        "Компанія змінила сервіс, а користувачі тепер бачать новий режим, який працює інакше, але старі налаштування лишаються доступними для всіх, хто не хоче нічого перемикати вручну й може працювати як раніше.\n\n"
        "Решта функцій працює без окремих змін для всіх користувачів."
    )
    quality = assess_rewrite(body, hard_limit=900)
    assert quality.score == 77
    assert 60 <= quality.score < 82


def test_rc40_safe_77_candidate_survives_failed_targeted_repair(monkeypatch) -> None:
    from telegram_autopilot.ai_router import AIRouterError, Result
    from telegram_autopilot.models import Channel
    from telegram_autopilot import production_pipeline as production_module
    from telegram_autopilot import rc37_policy as rc37_module
    from telegram_autopilot import rc38_policy as rc38_module
    from telegram_autopilot.rc40_policy import install_rc40_policy

    channel = Channel(
        id=1, name="CTRL+UA", telegram_chat_id="-1001",
        editorial_profile="Technology, science, AI, security", enabled=True,
        include_source_link=True, poll_interval_minutes=10,
        min_publish_interval_minutes=20, dedupe_window_hours=48,
        max_age_hours=24, max_posts_per_cycle=3,
        created_at="2026-08-26T00:00:00Z", updated_at="2026-08-26T00:00:00Z",
    )
    article = {
        "id": 404,
        "title": "Service changes notification mode",
        "raw_text": "The company changed how the service works. Existing settings remain available for users. No other functions changed.",
        "source_published_at": "2026-08-26T08:00:00Z",
        "teaser_text": "", "event_summary": "", "full_article_uk": "",
    }
    russian = (
        "Это внутренняя редакторская заметка. Главное здесь в изменении привычного режима, но старые настройки остаются доступными. "
        "Источник не говорит о других изменениях, поэтому следующий редактор должен сохранить этот простой конфликт и не добавлять ничего нового. "
        "Такой угол позволяет рассказать новость прямо, без лишнего пересказа и без выдуманных последствий."
    )
    ua_safe_77 = (
        "Компанія змінила сервіс, а користувачі тепер бачать новий режим, який працює інакше, але старі налаштування лишаються доступними для всіх, хто не хоче нічого перемикати вручну й може працювати як раніше.\n\n"
        "Решта функцій працює без окремих змін для всіх користувачів."
    )
    calls = []

    def fake_run_ai(prompt, validator=None, **kwargs):
        calls.append((prompt, kwargs.get("allowed_providers")))
        if "ВНУТРЕННИЙ редакторский проход" in prompt:
            result = Result(russian, "groq", "bridge-model", "Groq bridge", ("Groq bridge",))
        elif "RC40 TARGETED COPY-EDIT" in prompt:
            raise AIRouterError("repair unavailable")
        else:
            result = Result(ua_safe_77, "codex", "codex", "Codex", ("Codex",))
        if validator is not None:
            validator(result.text)
        return result

    monkeypatch.setattr(production_module, "run_ai", fake_run_ai)
    monkeypatch.setattr(production_module, "_title_duplicate", lambda article, recent: None)
    monkeypatch.setattr(production_module, "_deterministic_reject_reason", lambda article: "")
    monkeypatch.setattr(production_module, "apply_local_languagetool_detailed", lambda body, **kwargs: type("LT", (), {"text": body, "changes": 0})())
    monkeypatch.setattr(rc37_module, "newsworthiness_reject_reason", lambda article: "")
    monkeypatch.setattr(rc38_module, "topic_balance_reject_reason", lambda article, recent: "")

    install_rc40_policy()
    decision = production_module.decide(channel, article, [], hard_limit=900)
    assert decision.decision == "publish"
    assert decision.telegram_teaser == ua_safe_77
    assert "editorial quality 77/100" in decision.reason
    assert any("RC40 TARGETED COPY-EDIT" in prompt for prompt, _ in calls)
