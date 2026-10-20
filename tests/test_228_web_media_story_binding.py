"""2.2.8 P0: The Register Maxwell article must never inherit a related-story image.

The gate is applied to source-owned editorial WEB images, not Telegram exact-post
media. A photo successfully sent to Telegram is not proof it belongs to the news.
"""
from __future__ import annotations

import json

from telegram_autopilot.article_extractor import extract_article_content
from telegram_autopilot import media_pipeline


SOURCE = (
    "https://www.theregister.com/ai-and-ml/2026/10/19/"
    "maxwell-gives-sub-optimal-code-a-runtime-glow-up/5303961"
)
WRONG = "https://image.theregister.com/5303967.webp?width=1200"
RIGHT = "https://image.theregister.com/5303961.webp?width=1200"


def _probe(item, *, marketing_context=False):
    item.mime_type = "image/webp"
    item.width, item.height = 1200, 650
    item.digest = f"fake-{item.url}"
    item.data = b"mock"
    return item


def test_article_extractor_retains_thumbnail_destination_for_provenance():
    html = """<html><head><title>Maxwell makes code faster</title></head><body>
    <article><h1>Maxwell makes code faster</h1>
    <p>Maxwell continuously optimizes code while the program runs.</p>
    <p>It adapts instruction sequences to the available hardware.</p>
    <a href="/ai-and-ml/2026/10/19/another-story/5303967">
      <img alt="Maxwell AI optimization" width="1200" height="650"
           src="https://image.theregister.com/5303967.webp?width=1200">
    </a>
    </article></body></html>"""
    layout = json.loads(extract_article_content(html, SOURCE).layout_json)
    images = [b for b in layout["blocks"] if b.get("type") == "media"]
    assert len(images) == 1
    assert images[0]["linked_page_url"].endswith("/another-story/5303967")


def test_same_publisher_foreign_story_card_rejected_even_with_fake_strong_alt(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _probe)
    layout = json.dumps({"blocks": [{
        "type": "media", "index": 1, "kind": "image", "position": 0.01,
        "url": WRONG, "alt": "Maxwell code optimized at runtime",
        "schema_verified": True,
        "linked_page_url": "https://www.theregister.com/2026/10/19/unrelated/5303967",
    }]})
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Maxwell optimizes code", article_text="Maxwell improves runtimes",
        source_url=SOURCE,
    )
    assert not prepared.body
    assert prepared.drop_reasons == {"linked_other_article": 1}


def test_real_operator_wrong_image_id_blocked_without_ancestor_link(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _probe)
    layout = json.dumps({"blocks": [{
        "type": "media", "index": 1, "kind": "image", "position": 0.01,
        "url": WRONG, "alt": "", "caption": "",
        "schema_verified": True, "page_declared": True,
    }]})
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Maxwell gives sub-optimal code a runtime glow-up",
        article_text="Maxwell evaluates and optimizes binary execution", source_url=SOURCE,
    )
    assert not prepared.body
    assert prepared.drop_reasons == {"cross_article_image_id": 1}


def test_matching_story_image_is_preserved(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _probe)
    layout = json.dumps({"blocks": [{
        "type": "media", "index": 1, "kind": "image", "position": 0.05,
        "url": RIGHT, "alt": "Maxwell running AI code", "schema_verified": True,
        "linked_page_url": SOURCE,
    }]})
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Maxwell improves AI code", article_text="Maxwell optimizes runtime",
        source_url=SOURCE,
    )
    assert [item.url for item in prepared.body] == [RIGHT]


def test_zoom_link_does_not_look_like_another_article(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _probe)
    layout = json.dumps({"blocks": [{
        "type": "media", "index": 1, "kind": "image", "position": 0.05,
        "url": RIGHT, "alt": "Maxwell running AI code", "schema_verified": True,
        "linked_page_url": "https://www.theregister.com/images/maxwell-large.jpg",
    }]})
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Maxwell improves AI code", article_text="Maxwell optimizes runtime",
        source_url=SOURCE,
    )
    assert [item.url for item in prepared.body] == [RIGHT]


def test_other_publisher_page_declared_lede_is_not_globally_banned(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _probe)
    url = "https://cdn.example.org/agency/real-featured.jpeg"
    layout = json.dumps({
        "page_image_assets": [media_pipeline._media_identity(url)],
        "blocks": [{"type": "media", "index": 1, "kind": "image",
                    "position": 0.2, "url": url, "alt": "Cropped art",
                    "context": "article hero", "linked_page_url": "",
                    "schema_verified": True}],
    })
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="New campaign challenges viewers",
        article_text="The company launched a visual campaign.",
        source_url="https://news.example.org/story-new-campaign",
    )
    assert [item.url for item in prepared.body] == [url]


def test_no_source_images_means_no_invented_media():
    prepared = media_pipeline.prepare_article_media(
        json.dumps({"blocks": [], "featured": ""}), [],
        title="Maxwell improves runtime performance", article_text="Program optimization.",
        source_url=SOURCE,
    )
    assert prepared.featured is None
    assert prepared.body == []
