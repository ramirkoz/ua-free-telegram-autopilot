from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from telegram_autopilot.article_extractor import extract_article_content
from telegram_autopilot.database import Database
from telegram_autopilot.decision_engine import _marker_rewrite, build_decision_prompt, build_rewrite_prompt
from telegram_autopilot.language import normalize_ukrainian_terminology, sanitize_media_caption, terminology_issues
from telegram_autopilot.local_ai_runtime import choose_ollama_model
from telegram_autopilot.media_pipeline import PreparedMedia, _hard_reject, _score
from telegram_autopilot.models import Channel


def _channel() -> Channel:
    return Channel(1, "Tech", "@tech", "science and technology", True, False, 5, 10, 72, 24, 3, "x", "x")


def _article(**overrides):
    base = {
        "id": 1, "source_name": "Ars", "title": "Radiation-blocking vest flown to the Moon and back worked in test",
        "url": "https://example.com/story", "source_published_at": "2026-08-17T10:00:00Z",
        "raw_text": "Researchers tested a radiation shielding vest during a lunar mission. Measurements showed lower exposure in protected areas. " * 120,
        "article_layout_json": "",
    }
    base.update(overrides)
    return base


def test_rc8_database_rows_survive_rc9_initialization(tmp_path: Path):
    path = tmp_path / "telegram_autopilot.sqlite3"
    db = Database(path)
    with db.connect() as con:
        con.execute("INSERT INTO channels(name,telegram_chat_id,editorial_profile,enabled,include_source_link,poll_interval_minutes,min_publish_interval_minutes,dedupe_window_hours,max_age_hours,max_posts_per_cycle,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("Existing", "@existing", "tech", 1, 0, 5, 10, 72, 24, 3, "old", "old"))
        before = con.execute("SELECT id,name,telegram_chat_id FROM channels").fetchall()
    Database(path)
    with sqlite3.connect(path) as con:
        after = con.execute("SELECT id,name,telegram_chat_id FROM channels").fetchall()
    assert [tuple(x) for x in before] == after


def test_known_ukrainian_calques_are_normalized():
    text = normalize_ukrainian_terminology("Дані продавали на темному ринку, а старий телевізор мав електронно-лумову трубку.")
    assert "даркнет-майданчику" in text
    assert "електронно-променеву трубку" in text
    assert not terminology_issues(text)


def test_caption_requires_source_metadata_and_rejects_invented_claims():
    assert sanitize_media_caption("Фото лабораторії", "", "") == ""
    assert sanitize_media_caption("Зображення підтверджує, що система безпечна", "SafePal logo", "") == ""
    assert sanitize_media_caption("Випробування жилета під час місії", "Vest test during the mission", "")
    assert sanitize_media_caption("Під час тесту рівень упав на 42%", "Vest test during mission", "") == ""


def test_ollama_selection_avoids_embedding_models():
    chosen = choose_ollama_model(["nomic-embed-text:latest", "qwen3:4b", "llama3.2:3b"])
    assert chosen == "qwen3:4b"


def test_cocoon_and_banner_media_are_hard_rejected():
    assert _hard_reject(PreparedMedia(1, "image", "https://cdn.example.com/cocoon-ai-summary-banner.jpg"))
    assert _hard_reject(PreparedMedia(1, "image", "https://cdn.example.com/company-logo.png"))


def test_body_editorial_image_beats_generic_featured_image():
    title = "Radiation blocking vest flown to Moon works in test"
    body = "Astronaut lunar mission radiation vest shielding measurements"
    featured = PreparedMedia(0, "image", "https://cdn.example.com/generic-homepage.jpg", featured=True, width=1200, height=630)
    body_img = PreparedMedia(1, "image", "https://cdn.example.com/lunar-radiation-vest-test.jpg", caption="Radiation vest during lunar test", width=1400, height=900)
    featured.classification = body_img.classification = "photo"
    assert _score(body_img, title=title, article_text=body) > _score(featured, title=title, article_text=body)


def test_article_extractor_rejects_cocoon_and_ad_images():
    html = '''<html><head><title>Moon radiation vest test</title><meta property="og:image" content="https://cdn.example.com/cocoon-ai-summary-banner.jpg"></head>
    <body><article><p>Researchers tested a radiation vest around the Moon and measured its shielding performance in flight.</p>
    <div class="advertisement"><img src="https://cdn.example.com/buy-now-banner.jpg" width="1200" height="400"></div>
    <figure><img src="https://cdn.example.com/radiation-vest-moon.jpg" alt="Radiation vest tested around the Moon" width="1200" height="800"><figcaption>The test vest used during the mission.</figcaption></figure>
    </article></body></html>'''
    out = extract_article_content(html, "https://example.com/story")
    layout = json.loads(out.layout_json)
    assert not layout.get("featured")
    media = [b for b in layout["blocks"] if b.get("type") == "media"]
    assert len(media) == 1
    assert "radiation-vest-moon.jpg" in media[0]["url"]
    assert "test vest" in media[0]["caption"].casefold()


def test_ai_prompts_are_bounded():
    article = _article(raw_text="A" * 60000)
    decision_cloud = build_decision_prompt(_channel(), article, [], local=False)
    decision_local = build_decision_prompt(_channel(), article, [], local=True)
    rewrite_cloud, *_ = build_rewrite_prompt(_channel(), article, local=False)
    rewrite_local, *_ = build_rewrite_prompt(_channel(), article, local=True)
    assert len(decision_cloud) < 24000
    assert len(decision_local) < 15000
    assert len(rewrite_cloud) < 26000
    assert len(rewrite_local) < 16000


def test_local_rewrite_marker_protocol_is_tolerated():
    parsed = _marker_rewrite("ЗАГОЛОВОК: Новий матеріал про технологію\nАНОНС: Це достатньо довгий анонс для перевірки локального формату.\nТЕКСТ: Повний текст починається тут і може містити кілька абзаців.")
    assert parsed and parsed["headline_uk"].startswith("Новий матеріал")
