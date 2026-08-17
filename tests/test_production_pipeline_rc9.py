from __future__ import annotations

import sqlite3

import pytest

from telegram_autopilot.ai_router import Result
from telegram_autopilot.models import Channel
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
**HEADLINE:** Новий український заголовок про технологію
**TEASER:** Український анонс достатньої довжини, який пояснює головний факт новини без зайвої реклами.
**ARTICLE:** Це готовий український текст матеріалу. Він містить достатньо фактів і пояснює головну подію без вигаданих деталей. Друге речення додає потрібний контекст для читача. Третє речення робить текст достатньо повним для публікації у Telegraph.
```"""
    parsed = validate_rewrite(raw)
    assert parsed["headline"].startswith("Новий")
    assert "готовий" in parsed["full"]


def test_decide_spends_one_ai_call_only(monkeypatch):
    row = _row(
        "Nvidia discloses a major new interconnect design",
        "Nvidia disclosed a new interconnect design for AI clusters. It doubles bandwidth to 800 Gbit/s while keeping power use unchanged. Engineers said production begins next quarter. " * 3,
    )
    calls = []

    def fake_run_ai(prompt, **kwargs):
        calls.append((prompt, kwargs))
        text = """ЗАГОЛОВОК: Nvidia представила нову архітектуру інтерконекту
АНОНС: Nvidia представила нову архітектуру з'єднання для ШІ-кластерів, яка подвоює пропускну здатність до 800 Гбіт/с без збільшення енергоспоживання.
ТЕКСТ: Nvidia представила нову архітектуру з'єднання для ШІ-кластерів. За даними компанії, вона подвоює пропускну здатність до 800 Гбіт/с без збільшення енергоспоживання. Інженери повідомили, що виробництво має розпочатися наступного кварталу. Рішення призначене для з'єднання обчислювальних вузлів у великих системах."""
        return Result(
            text=text,
            provider="groq",
            model="openai/gpt-oss-120b",
            label="GPT-OSS 120B / Groq",
            attempted=("GPT-OSS 120B / Groq",),
        )

    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.run_ai", fake_run_ai)
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    result = decide(_channel(), row, [])
    assert result.decision == "publish"
    assert result.provider == "groq"
    assert len(calls) == 1
    assert len(calls[0][0]) < 4500
    assert calls[0][1]["local_max_output_tokens"] == 460


def test_deal_reject_uses_no_ai(monkeypatch):
    row = _row("Best laptop deal: buy now for $599", "This discounted laptop is on sale now. Use our affiliate links.")
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.run_ai", lambda *a, **k: pytest.fail("AI must not run"))
    result = decide(_channel(), row, [])
    assert result.decision == "reject"
    assert result.provider == "local-rule"
