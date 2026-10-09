from __future__ import annotations

import json
from types import SimpleNamespace

from telegram_autopilot import article_extractor, media_pipeline
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle


def _layout(blocks=None, *, featured="", provenance=""):
    return json.dumps({
        "blocks": blocks or [],
        "featured": featured,
        "featured_meta": {"provenance": provenance, "alt": "generic photo"},
    })


def test_211_fallback_media_kept_when_html_has_unrelated_media_block():
    layout = _layout([{"type": "media", "kind": "iframe", "url": "https://youtube.com/embed/abcdefgh"}])
    featured, body = media_pipeline._layout_items(
        layout, ["image|https://cdn.example.com/robot-conference-hero.jpg"]
    )
    assert featured is None
    assert any(x.url.endswith("robot-conference-hero.jpg") for x in body)


def test_211_verified_article_hero_survives_generic_alt_after_binary_probe(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", lambda item, **kw: item)
    source = "https://cdn.example.com/photo123.jpg"
    prepared = media_pipeline.prepare_article_media(
        _layout(featured=f"image|{source}", provenance="page_hero"), [],
        title="New robotic chip unveiled", article_text="A new robotic chip...",
    )
    assert prepared.featured is not None
    assert prepared.featured.url == source
    assert prepared.featured.relevance_score >= 38


def test_211_verified_article_gallery_survives_opaque_filenames(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", lambda item, **kw: item)
    images = [
        {"type": "media", "kind": "image", "url": f"https://cdn.example.com/photo{i}.jpg",
         "context": "schema article gallery", "gallery": True,
         "schema_verified": True, "position": 0.05}
        for i in (1, 2, 3)
    ]
    prepared = media_pipeline.prepare_article_media(
        _layout(images), [], title="Robotic device unveiled", article_text="A new robotic device...",
    )
    assert len([x for x in prepared.body if x.gallery]) == 3


def test_211_unbound_jsonld_single_story_is_not_trusted():
    html = """<html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"NewsArticle",
     "headline":"Unrelated marketing banner",
     "mainEntityOfPage":"https://example.com/other-story",
     "image":"https://example.com/ads-promo.jpg"}
    </script></head><body><article><h1>Robotic surgery breakthrough</h1><p>Article text.</p></article></body></html>"""
    assert article_extractor._jsonld_article_image_candidates(
        html, "https://example.com/robotic-surgery", "Robotic surgery breakthrough"
    ) == []


def test_211_media_validation_failure_is_observable(monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("simulated image validation error")
    monkeypatch.setattr(media_pipeline, "prepare_article_media", failure)
    article = {
        "id": 123, "title": "Robotic surgery breakthrough", "raw_text": "Interesting story",
        "final_text": "", "media_json": '["image|https://example.com/robot.jpg"]',
        "article_layout_json": "{}",
    }
    channel = SimpleNamespace(mode=ChannelMode.EDITORIAL, editorial_runtime_profile="standard")
    bundle = build_publication_media_bundle(channel, article)
    assert bundle.count == 0
    assert bundle.extracted_media_count == 1
    assert bundle.filtered_media_count == 1
    assert "RuntimeError" in bundle.media_validation_error


def test_211_near_identical_gallery_images_are_not_published_twice(monkeypatch):
    def probe(item, **kwargs):
        item.width, item.height = 1200, 800
        item.digest = item.url
        item.perceptual_hash = "1234567890abcdef"
        return item
    monkeypatch.setattr(media_pipeline, "_probe_image", probe)
    images = [
        {"type": "media", "kind": "image", "url": f"https://cdn.example.com/photo-{i}.jpg",
         "context": "schema article gallery", "gallery": True,
         "schema_verified": True, "position": 0.05}
        for i in (1, 2)
    ]
    result = media_pipeline.prepare_article_media(_layout(images), [],
                                                  title="Robot prototype", article_text="Robot prototype unveiled")
    assert len(result.body) == 1


def test_211_perceptual_hash_survives_image_resize():
    from PIL import Image
    from io import BytesIO
    im = Image.new("RGB", (90, 80))
    for y in range(80):
        for x in range(90):
            im.putpixel((x, y), (x * 2, y * 3, (x + y) % 255))
    def dump(image):
        b = BytesIO()
        image.save(b, format="PNG")
        return b.getvalue()
    first = media_pipeline._perceptual_hash(dump(im))
    resized = media_pipeline._perceptual_hash(dump(im.resize((180, 160))))
    assert first and resized
    assert (int(first, 16) ^ int(resized, 16)).bit_count() <= 3
