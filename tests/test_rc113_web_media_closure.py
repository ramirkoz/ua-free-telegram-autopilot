from __future__ import annotations

import json

from telegram_autopilot.article_extractor import extract_article_content


def test_rc113_recovers_article_bound_page_hero_outside_article() -> None:
    html = """
    <html>
      <head>
        <title>New research: Avoid these 3-word phrases if you don't want to sound like AI</title>
      </head>
      <body>
        <article>
          <h1>New research: Avoid these 3-word phrases if you don't want to sound like AI</h1>
          <p>Researchers found several phrases that make ordinary writing sound machine generated.</p>
        </article>
        <div class="visual-shell">
          <img
            src="https://cdn.example.com/ai-writing-research.jpg"
            width="1200"
            height="700"
            alt="New research: Avoid these 3-word phrases if you don't want to sound like AI"
          />
        </div>
      </body>
    </html>
    """
    out = extract_article_content(
        html,
        "https://www.fastcompany.com/91617559/new-research-3-word-phrases-that-sound-like-ai-generated-writing-chatgpt",
    )
    assert out.media_urls == ["https://cdn.example.com/ai-writing-research.jpg"]
    layout = json.loads(out.layout_json)
    assert layout["featured"] == "https://cdn.example.com/ai-writing-research.jpg"
    assert layout["featured_meta"]["provenance"] == "page_hero"
    assert layout["media_diagnostics"]["page_image_candidates"] == 1
    assert layout["media_diagnostics"]["selected_provenance"] == "page_hero"


def test_rc113_rejects_unrelated_page_image_outside_article() -> None:
    html = """
    <html>
      <head><title>New research on AI writing habits</title></head>
      <body>
        <article>
          <h1>New research on AI writing habits</h1>
          <p>The article discusses language patterns and writing habits.</p>
        </article>
        <div class="recommendation-card">
          <img
            src="https://cdn.example.com/summer-travel-resort.jpg"
            width="1200"
            height="700"
            alt="Luxury summer travel resort"
          />
        </div>
      </body>
    </html>
    """
    out = extract_article_content(html, "https://example.com/new-research-ai-writing-habits")
    assert out.media_urls == []
    layout = json.loads(out.layout_json)
    assert layout["featured"] == ""
    assert layout["media_diagnostics"]["page_image_candidates"] == 0


def test_rc113_explicit_hero_wrapper_can_recover_weak_alt() -> None:
    html = """
    <html>
      <head><title>Stone jackets turn slate into clothing</title></head>
      <body>
        <article>
          <h1>Stone jackets turn slate into clothing</h1>
          <p>A fashion company built a wearable jacket using thin slate tiles.</p>
        </article>
        <div class="story-hero">
          <img src="https://cdn.example.com/hero-3918.jpg" width="1400" height="900" alt="Campaign image"/>
        </div>
      </body>
    </html>
    """
    out = extract_article_content(html, "https://example.com/stone-jackets-slate-clothing")
    assert out.media_urls == ["https://cdn.example.com/hero-3918.jpg"]
    layout = json.loads(out.layout_json)
    assert layout["featured_meta"]["provenance"] == "page_hero"
