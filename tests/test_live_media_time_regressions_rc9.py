from __future__ import annotations

import json
import sqlite3

import pytest

from telegram_autopilot.article_extractor import extract_article_content
from telegram_autopilot.media_pipeline import PreparedArticleMedia, PreparedMedia, _score
from telegram_autopilot.models import Channel
from telegram_autopilot.production_pipeline_rc9 import build_rewrite_prompt, validate_rewrite


def _channel() -> Channel:
    return Channel(
        1, "CTRL+UA", "@ctrlua", "Technology and science", True, False,
        5, 0, 72, 24, 3, "2026-08-17T00:00:00+00:00", "2026-08-17T00:00:00+00:00",
    )


def _dated_row(title: str, raw_text: str, published: str = "2026-08-17T10:24:35-04:00"):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE x(id INTEGER, title TEXT, raw_text TEXT, source_published_at TEXT)")
    conn.execute("INSERT INTO x VALUES(?,?,?,?)", (1, title, raw_text, published))
    return conn.execute("SELECT * FROM x").fetchone()


def test_article_scope_excludes_related_story_images_inside_main():
    html = '''<html><head><title>Uber and Zipline drone delivery</title></head><body>
    <main>
      <article>
        <p>Uber Eats and Zipline will start drone deliveries later this year in Dallas-Fort Worth.</p>
        <figure><img src="https://cdn.example.com/uber-zipline-drone.jpg" alt="Zipline drone delivering an Uber Eats order" width="1400" height="900"></figure>
        <p>The companies target one million daily deliveries by 2029.</p>
      </article>
      <section class="more-stories">
        <img src="https://cdn.example.com/jaguar-interior.jpg" alt="Jaguar interior" width="1800" height="1200">
        <img src="https://cdn.example.com/corvette.jpg" alt="Corvette sports car" width="1800" height="1200">
      </section>
    </main></body></html>'''
    out = extract_article_content(html, "https://www.theverge.com/story")
    layout = json.loads(out.layout_json)
    urls = [b.get("url", "") for b in layout["blocks"] if b.get("type") == "media"]
    assert urls == ["https://cdn.example.com/uber-zipline-drone.jpg"]
    assert "Jaguar" not in out.text


def test_unrelated_late_large_image_cannot_beat_relevant_article_image():
    title = "Uber and Zipline start drone delivery for Uber Eats"
    body = "Uber Eats Zipline drone delivery Dallas Fort Worth one million deliveries by 2029"
    relevant = PreparedMedia(
        1, "image", "https://cdn.example.com/uber-zipline-drone.jpg",
        alt="Zipline drone delivers Uber Eats order", position=0.05, width=1400, height=900,
        data=b"image",
    )
    unrelated = PreparedMedia(
        2, "image", "https://cdn.example.com/jaguar-interior.jpg",
        alt="Jaguar vehicle interior", position=0.85, width=2400, height=1600,
        data=b"image",
    )
    relevant.classification = unrelated.classification = "photo"
    relevant.relevance_score = _score(relevant, title=title, article_text=body)
    unrelated.relevance_score = _score(unrelated, title=title, article_text=body)
    assert relevant.relevance_score >= 38
    assert unrelated.relevance_score < 38
    assert PreparedArticleMedia(None, [relevant, unrelated]).telegram_hero is relevant


def test_prompt_anchors_relative_time_to_source_publication_date():
    row = _dated_row(
        "Uber partners with Zipline on Eats drone deliveries",
        "Uber Eats deliveries will start later this year in Dallas-Fort Worth and reach one million daily deliveries by 2029.",
    )
    prompt = build_rewrite_prompt(_channel(), row)
    assert "SOURCE PUBLICATION DATE: 2026-08-17" in prompt
    assert "never 2024" in prompt


def test_rewrite_rejects_invented_calendar_year(monkeypatch):
    monkeypatch.setattr("telegram_autopilot.production_pipeline_rc9.looks_ukrainian", lambda value: True)
    bad = """ЗАГОЛОВОК: Uber і Zipline запускають доставку дронами
АНОНС: Uber Eats і Zipline планують у 2024 році почати доставку їжі дронами в районі Даллас-Форт-Ворт.
ТЕКСТ: Uber Eats і Zipline планують у 2024 році запустити доставку їжі дронами в районі Даллас-Форт-Ворт. Компанії також заявили про мету досягти мільйона доставок на день до 2029 року. Zipline працює в Техасі з 2025 року."""
    with pytest.raises(Exception, match="вигадав рік"):
        validate_rewrite(bad, allowed_years={2025, 2026, 2029})
