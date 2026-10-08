from __future__ import annotations

import json

from telegram_autopilot.article_extractor import extract_article_content


def test_202_rejects_unrelated_page_level_video_on_article_page() -> None:
    html = """
    <html>
      <head>
        <title>Big Tech is cutewashing its AI agents</title>
        <meta property="og:title" content="Big Tech is cutewashing its AI agents"/>
        <meta property="og:url" content="https://www.fastcompany.com/91620091/big-tech-is-cutewashing-its-ai-agents"/>
        <meta property="og:type" content="article"/>
        <meta property="og:video" content="https://cdn.example.com/video/91234567-unrelated-awards-player.mp4"/>
        <meta property="og:image" content="https://cdn.example.com/91620091-ai-agents-hero.jpg"/>
        <meta property="og:image:alt" content="Big Tech is cutewashing its AI agents"/>
      </head>
      <body>
        <article>
          <h1>Big Tech is cutewashing its AI agents</h1>
          <p>Companies are giving AI agents cute names, mascots, and human-like identities.</p>
        </article>
      </body>
    </html>
    """
    out = extract_article_content(
        html,
        "https://www.fastcompany.com/91620091/big-tech-is-cutewashing-its-ai-agents",
    )
    assert not any("91234567-unrelated-awards-player" in item for item in out.media_urls)
    layout = json.loads(out.layout_json)
    assert layout["featured_video"] == ""
    assert layout["media_diagnostics"]["video_provenance"] == "rejected_unbound_page_video"


def test_202_accepts_article_body_youtube_embed() -> None:
    html = """
    <html>
      <head><title>AI agent design explained</title></head>
      <body>
        <article>
          <h1>AI agent design explained</h1>
          <p>This story includes its own explainer video.</p>
          <iframe src="https://www.youtube.com/embed/abc123" title="AI agent design explained"></iframe>
        </article>
      </body>
    </html>
    """
    out = extract_article_content(html, "https://example.com/ai-agent-design-explained")
    assert any(item == "iframe|https://www.youtube.com/embed/abc123" for item in out.media_urls)


def test_202_accepts_page_video_when_asset_contains_same_article_id() -> None:
    html = """
    <html>
      <head>
        <title>Big Tech is cutewashing its AI agents</title>
        <meta property="og:title" content="Big Tech is cutewashing its AI agents"/>
        <meta property="og:url" content="https://www.fastcompany.com/91620091/big-tech-is-cutewashing-its-ai-agents"/>
        <meta property="og:video" content="https://cdn.example.com/video/91620091-player.mp4"/>
      </head>
      <body>
        <article>
          <h1>Big Tech is cutewashing its AI agents</h1>
          <p>Article body text.</p>
        </article>
      </body>
    </html>
    """
    out = extract_article_content(
        html,
        "https://www.fastcompany.com/91620091/big-tech-is-cutewashing-its-ai-agents",
    )
    assert any("91620091-player.mp4" in item for item in out.media_urls)
    layout = json.loads(out.layout_json)
    assert layout["media_diagnostics"]["video_provenance"] == "bound_page_video"
