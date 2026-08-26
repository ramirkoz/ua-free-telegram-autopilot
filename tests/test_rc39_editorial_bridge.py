from __future__ import annotations

import pytest

from telegram_autopilot.models import Channel
from telegram_autopilot.production_pipeline import ProductionPipelineError
from telegram_autopilot.rc39_policy import (
    anti_slop_issues,
    build_russian_editorial_prompt,
    build_ukrainian_bridge_prompt,
    validate_russian_editorial,
)


def _channel() -> Channel:
    return Channel(
        id=1,
        name="CTRL+UA",
        telegram_chat_id="-1001",
        editorial_profile="Technology, science, AI, security",
        enabled=True,
        include_source_link=True,
        poll_interval_minutes=10,
        min_publish_interval_minutes=20,
        dedupe_window_hours=48,
        max_age_hours=24,
        max_posts_per_cycle=3,
        created_at="2026-08-26T00:00:00Z",
        updated_at="2026-08-26T00:00:00Z",
    )


def _article() -> dict[str, object]:
    return {
        "id": 99,
        "title": "A strange camera case becomes a criminal prosecution",
        "raw_text": (
            "Police installed a 3D-printed decoy camera as part of an operation. "
            "A man later removed and damaged the decoy. The mayor said the decoy itself cost nothing. "
            "Police documents nevertheless described the damage using the replacement price of a real device. "
            "The case resulted in criminal charges."
        ),
        "source_published_at": "2026-08-25T12:00:00Z",
        "teaser_text": "",
        "event_summary": "",
        "full_article_uk": "",
    }


def test_rc39_russian_bridge_prompt_is_editorial_not_translation() -> None:
    prompt = build_russian_editorial_prompt(_channel(), _article(), hard_limit=900)
    low = prompt.casefold()
    assert "русский редакторский черновик" in low
    assert "не переводи источник по абзацам" in low
    assert "source evidence pack" in low
    assert "55–80" not in prompt
    assert "3–5" not in prompt


def test_rc39_ukrainian_prompt_rewrites_from_zero_not_sentence_translation() -> None:
    russian = (
        "История выглядит абсурдно: полиция поставила пластиковую приманку, а уголовное дело появилось после того, "
        "как мужчина её сломал. Главный редакторский угол здесь не цена устройства, а разрыв между тем, сколько стоил "
        "муляж, и тем, как ущерб описали в документах."
    )
    prompt = build_ukrainian_bridge_prompt(_channel(), _article(), russian, hard_limit=900)
    low = prompt.casefold()
    assert "не перекладай російську чернетку речення за реченням" in low
    assert "напиши текст заново" in low
    assert "єдине джерело фактів" in low
    assert "немає фіксованої кількості слів, речень або абзаців" in low
    assert "650–890" in prompt


def test_rc39_accepts_natural_russian_internal_draft() -> None:
    text = (
        "История здесь не в самой технологии, а в том, как обычный полицейский эксперимент превратился в уголовное дело. "
        "Полиция поставила пластиковую приманку и наблюдала за ней, пока мужчина не снял устройство. Это уже звучит странно, "
        "но дальше становится ещё интереснее.\n\n"
        "Сам муляж ничего не стоил, потому что его сделали как часть внутренней операции. При этом в документах ущерб описали "
        "через стоимость настоящего устройства. Для читателя это и есть главный конфликт истории: реальная цена одного предмета "
        "и юридическая оценка последствий оказались разными вещами.\n\n"
        "Черновик не должен додумывать мотивы полиции или обвиняемого. Он лишь выстраивает факты так, чтобы следующему редактору "
        "было понятно, почему история цепляет и что в ней стоит оставить."
    )
    assert validate_russian_editorial(text, allowed_years=set(), allowed_numbers=set()) == text


def test_rc39_rejects_ukrainian_text_as_russian_bridge() -> None:
    text = (
        "Це український текст, який спеціально написаний досить довго для перевірки мовного шлюзу. "
        "Він містить природні українські слова, літери і конструкції, тому не повинен пройти як російська редакторська чернетка. "
        "Система має відрізняти робочий російський шар від фінального українського тексту і не змішувати ці ролі. "
        "Саме для цього тут є окрема перевірка перед другим авторським проходом."
    )
    with pytest.raises(ProductionPipelineError, match="RU bridge"):
        validate_russian_editorial(text, allowed_years=set(), allowed_numbers=set())


def test_rc39_russian_bridge_rejects_invented_number() -> None:
    text = (
        "Это нормальный русский редакторский черновик, который сначала выделяет главную историю, а потом оставляет только нужный контекст. "
        "Он не пытается переводить источник буквально и не превращает заметку в справку. При этом здесь специально появляется число 777, "
        "которого в исходных доказательствах нет. Если такой факт проходит дальше, второй автор может случайно принять его за настоящий. "
        "Поэтому внутренний мост обязан отбрасывать новые числа ещё до украинского текста."
    )
    with pytest.raises(ProductionPipelineError, match="число"):
        validate_russian_editorial(text, allowed_years=set(), allowed_numbers=set())


def test_rc39_anti_slop_allows_irregular_human_rhythm() -> None:
    body = (
        "Поліція надрукувала фальшиву камеру на 3D-принтері. І саме її поломка перетворилася на кримінальну справу.\n\n"
        "Муляж нічого не коштував, але збиток у документах рахували так, ніби зламали справжню систему. "
        "У цьому й уся дивина історії: пластикова приманка виявилася юридично дорожчою за саму себе."
    )
    assert anti_slop_issues(body) == ()


def test_rc39_anti_slop_rejects_canned_transition_stack() -> None:
    body = (
        "Паралельно компанія змінила правила. Для користувачів це означає ще один режим роботи.\n\n"
        "Окремо з'явився новий перемикач. Таким чином система стала гнучкішою.\n\n"
        "Варто зазначити, що йдеться про поступове розгортання."
    )
    issues = anti_slop_issues(body)
    assert any("AI-переход" in issue for issue in issues)
    assert any("шаблонними переходами" in issue for issue in issues)
