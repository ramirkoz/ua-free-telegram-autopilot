"""2.3.30: explicit source DOM widget ancestry beats CMS/gallery metadata.

#297 Naruto #961 is an operator-confirmed wrong-toolkit-image incident;
the exact original media hashes/DOM are still required for full acceptance.
These tests cover the independently verifiable failure mechanism without
pretending synthetic media are the three original Telegram attachments.
"""
import json

import pytest
from telegram_autopilot import media_pipeline


def _fake_image(item, *, marketing_context=False):
    item.mime_type = "image/jpeg"
    item.width, item.height = 1200, 800
    item.digest = item.url
    item.data = b"image"
    return item


@pytest.mark.parametrize("context", [
    "article-container sidebar related-stories",
    "related_posts carousel",
    "site-wide latest-posts rail",
    "recommendations commercial",
    "article-body read-next recommended",
    "product-widget in-article rail",
    "site-wide gear-up promotions",
])
def test_2330_widget_images_never_override_schema_gallery_flags(monkeypatch, context):
    monkeypatch.setattr(media_pipeline, "_probe_image", _fake_image)
    image = "https://cdn.creativebloq.com/images/unrelated-tools-1200.jpg"
    layout = json.dumps({
        "page_image_assets": [media_pipeline._media_identity(image)],
        "blocks": [{
            "type": "media", "index": 1, "kind": "image",
            "url": image, "position": 0.05, "gallery": True,
            "schema_verified": True, "alt": "Naruto puppet illustration",
            "caption": "Naruto scene", "context": context,
        }],
    })
    output = media_pipeline.prepare_article_media(
        layout, [], title="How I created this ninja puppet scene inspired by Naruto",
        article_text="Artist Guilherme Freitas illustrates a puppet scene inspired by Naruto.",
        source_url="https://www.creativebloq.com/how-to/how-i-created-this-ninja-puppet-scene-inspired-by-naruto",
        marketing_context=True,
    )
    assert not output.body
    assert output.drop_reasons.get("site_wide_widget_media_2330") == 1


def test_2330_genuine_story_gallery_is_not_suppressed(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _fake_image)
    urls = [
        "https://cdn.creativebloq.com/images/naruto-puppet-scene.jpg",
        "https://cdn.creativebloq.com/images/naruto-puppet-closeup.jpg",
    ]
    layout = json.dumps({
        "blocks": [{
            "type": "media", "index": i + 1, "kind": "image",
            "url": url, "position": (i + 1) * 0.1,
            "gallery": True, "schema_verified": True,
            "alt": "Naruto puppet artwork", "context": "article-body main-gallery figure",
        } for i, url in enumerate(urls)],
    })
    output = media_pipeline.prepare_article_media(
        layout, [], title="Artist creates a Naruto-inspired ninja puppet scene",
        article_text="Artist Guilherme Freitas illustrated a Naruto puppet with original artwork.",
        source_url="https://www.creativebloq.com/how-to/how-i-created-this-ninja-puppet-scene-inspired-by-naruto",
        marketing_context=True,
    )
    assert [item.url for item in output.body] == urls
    assert not output.drop_reasons.get("site_wide_widget_media_2330")


def test_2330_context_does_not_blacklist_legitimate_story_words():
    from telegram_autopilot.media_pipeline import PreparedMedia, _site_widget_media_2330
    assert not _site_widget_media_2330(PreparedMedia(
        1, "image", "https://cdn.example.com/story.jpg",
        caption="A review of popular design tools",
        context="article-body main-gallery figure",
    ))
