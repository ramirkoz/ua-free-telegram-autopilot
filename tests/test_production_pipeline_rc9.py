from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from telegram_autopilot.ai_router import Result
from telegram_autopilot.models import Channel, Decision
from telegram_autopilot.production_pipeline_rc9 import build_rewrite_prompt, decide, validate_rewrite


def _channel() -> Channel:
    return Channel(
        id=1, name="CTRL+UA", telegram_chat_id="@ctrlua", editorial_profile="Technology and science",
        enabled=True, include_source_link=False, poll_interval_minutes=5, min_publish_interval_minutes=0,
        dedupe_window_hours=72, max_age_hours=24, max_posts_per_cycle=3,
        created_at="2026-08-17T00:00:00+00:00", updated_at="2026-08-17T00:00:00+00:00",
    )


def _row(title: str, raw_text: str, article_id: int = 1):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE x(id INTEGER, title TEXT, raw_text TEXT)")
    conn.execute("INSERT INTO x VALUES(?,?,?)", (article_id, title, raw_text))
    return conn.execute("SELECT * FROM x").fetchone()


def test_prompt_is_bounded_for_cloud_and_local():
    row = _row("Nvidia announces new chip architecture", "Useful source sentence. " * 1000)
    assert len(build_rewrite_prompt(_channel(), row, local=False)) < 4500
    assert len(build_rewrite_prompt(_channel(), row, local=True)) < 3500


def test_parser_accepts_markdown_and_english_labels(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    raw = """```markdown
**HEADLINE:** Цей заголовок має бути проігнорований
**ARTICLE:** Це готовий український текст матеріалу. Він пояснює головну подію без вигаданих деталей.

Друге речення додає потрібний контекст для читача. Третє речення завершує матеріал природно.
```"""
    parsed = validate_rewrite(raw)
    assert parsed["headline"] == ""
    assert "готовий" in parsed["full"]
    assert "проігнорований" not in parsed["post"]


def test_decide_spends_one_ai_call_only(monkeypatch):
    row = _row(
        "Nvidia discloses a major new interconnect design",
        "Nvidia disclosed a new interconnect design for AI clusters. It doubles bandwidth to 800 Gbit/s while keeping power use unchanged. Engineers said production begins next quarter. " * 3,
    )
    calls = []

    def fake_run_ai(prompt, **kwargs):
        calls.append((prompt, kwargs))
        text = """ТЕКСТ: Nvidia представила нову архітектуру з'єднання для ШІ-кластерів. За даними компанії, вона подвоює пропускну здатність до 800 Гбіт/с без збільшення енергоспоживання.

Інженери повідомили, що виробництво має розпочатися наступного кварталу. Рішення призначене для з'єднання обчислювальних вузлів у великих системах."""
        return Result(text=text, provider="groq", model="openai/gpt-oss-120b", label="GPT-OSS 120B / Groq", attempted=("GPT-OSS 120B / Groq",))

    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.run_ai", fake_run_ai)
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    result = decide(_channel(), row, [])
    assert result.decision == "publish"
    assert result.provider == "groq"
    assert result.headline_uk == "\u200b"
    assert len(calls) == 1
    assert len(calls[0][0]) < 4500
    assert calls[0][1]["local_max_output_tokens"] == 720


def test_deal_reject_uses_no_ai(monkeypatch):
    row = _row("Best laptop deal: buy now for $599", "This discounted laptop is on sale now. Use our affiliate links.")
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.run_ai", lambda *a, **k: pytest.fail("AI must not run"))
    result = decide(_channel(), row, [])
    assert result.decision == "reject"
    assert result.provider == "local-rule"


def test_adaptive_verifier_keeps_good_first_draft_to_one_call(monkeypatch):
    row = _row(
        "New sensor detects toxic substances",
        "Researchers built a wearable sensor that detects toxic substances in water and air. The device uses microsensors and vibration alerts. " * 3,
    )
    calls = []

    def fake_run_ai(prompt, **kwargs):
        calls.append(prompt)
        return Result(
            text=(
                "ТЕКСТ: Дослідники створили носимий сенсор, який у реальному часі виявляє токсичні речовини у воді та повітрі. "
                "Пристрій використовує мікросенсори й попереджає людину вібрацією.\n\n"
                "Такий формат може бути корисним там, де небезпеку потрібно помітити без затримки. Автори розглядають систему як доповнення до звичних засобів контролю довкілля."
            ),
            provider="groq", model="m1", label="m1", attempted=("m1",),
        )

    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.run_ai", fake_run_ai)
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    result = decide(_channel(), row, [])
    assert result.decision == "publish"
    assert len(calls) == 1


def test_adaptive_verifier_requests_second_candidate_for_dense_draft(monkeypatch):
    row = _row(
        "Police officer discovers camera network",
        "A police officer found an unapproved network of license plate cameras. The cameras tracked vehicles across city roads. Officials had earlier rejected the system because of cost. " * 3,
    )
    calls = []
    dense = (
        "ТЕКСТ: Патрульний виявив мережу камер, яка охоплювала дороги міста та фіксувала автомобілі за номерними знаками, наклейками, багажниками, маршрутами й іншими ознаками, хоча систему раніше офіційно не погоджували.\n\n"
        "Пристрої вже працювали на ключових перехрестях і виїздах, тому така інфраструктура давала поліції інструмент пошуку машин і водночас створювала детальний масив даних про пересування звичайних людей."
    )
    better = (
        "ТЕКСТ: Патрульний помітив на міській дорозі камеру автоматичного розпізнавання номерів. Після перевірки він знайшов ще десятки таких пристроїв на перехрестях і виїздах з міста.\n\n"
        "Раніше поліція не погодила закупівлю цієї системи через високу вартість. Попри це, мережа вже збирала дані про маршрути автомобілів. Такий масштаб спостереження викликає питання не лише про боротьбу зі злочинністю, а й про приватність звичайних водіїв."
    )

    def fake_run_ai(prompt, **kwargs):
        calls.append((prompt, kwargs))
        text = dense if len(calls) == 1 else better
        provider = "groq" if len(calls) == 1 else "nvidia"
        return Result(text=text, provider=provider, model=provider, label=provider, attempted=(provider,))

    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.run_ai", fake_run_ai)
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    result = decide(_channel(), row, [])
    assert result.decision == "publish"
    assert len(calls) == 2
    assert result.provider == "nvidia"
    assert "Патрульний помітив" in result.telegram_teaser
    assert "SECOND-PASS QUALITY REVISION" in calls[1][0]
    assert "groq" in calls[1][1]["skip_providers"]
