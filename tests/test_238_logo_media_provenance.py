"""Regression for user-observed duplicate unrelated 2nd media in two logo posts."""
from __future__ import annotations

import json
from types import SimpleNamespace

import telegram_autopilot.media_pipeline as legacy
from telegram_autopilot.v2.domain import ChannelMode, EditorialRuntimeProfile
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle
from telegram_autopilot.v2.logo_media_provenance_238 import choose_identity_story_media_238


def _channel():
    return SimpleNamespace(mode=ChannelMode.EDITORIAL,
                           editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL)


def _probe(item, **kwargs):
    item.data = (str(item.url) + "jpg").encode()
    item.mime_type = "image/jpeg"
    item.width = 1200
    item.height = 800
    item.digest = item.url
    return item


def _article(article_id, title, raw_text, lead_url, unrelated_url):
    return {
        "id": article_id, "title": title, "raw_text": raw_text,
        "canonical_source_url": "https://www.creativebloq.com/news/" + str(article_id),
        "media_json": json.dumps([lead_url, unrelated_url]),
        "article_layout_json": json.dumps({
            "source_kind": "web",
            "featured": "image|" + unrelated_url,
            "featured_meta": {"provenance": "page_hero", "alt": "Design Inspiration"},
            "blocks": [{"type": "media", "kind": "image", "url": lead_url,
                        "alt": raw_text[:110], "caption": title,
                        "context": "article lead image", "position": 0.05},
                       {"type": "media", "kind": "image", "url": unrelated_url,
                        "alt": "Creative Tools", "context": "article related tools",
                        "position": 0.15}],
        }),
    }


def test_238_two_creativebloq_logo_posts_never_attach_shared_unrelated_image(monkeypatch):
    """88700 and 89671 are from operator snapshot, with 2 COMMITTED images each."""
    monkeypatch.setattr(legacy, "_probe_image", _probe)
    shared = "https://cdn.creativebloq.com/site-promo-design-inspiration.jpg"
    cases = [
        (88700, "The real star of the new MacBook Pro is the Apple logo",
         "Apple returned the illuminated logo on the MacBook Pro.",
         "https://cdn.creativebloq.com/apple-macbook-illuminated-logo.jpg"),
        (89671, "This clever logo design has been electrifying the internet since 2008",
         "Ed's Electric designed by Josiah Jost. Plug and socket form hidden letter E.",
         "https://cdn.creativebloq.com/eds-electric-plug-socket-logo.jpg"),
    ]
    for article_id, title, source, actual in cases:
        bundle = build_publication_media_bundle(
            _channel(), _article(article_id, title, source, actual, shared)
        )
        assert [x.url for x in bundle.items] == [actual], article_id
        assert dict(bundle.drop_reasons).get("identity_story_unproven_extra_238", 0) >= 1


def test_238_verified_logo_asset_not_rejected_as_site_icon(monkeypatch):
    monkeypatch.setattr(legacy, "_probe_image", _probe)
    legitimate = legacy.PreparedMedia(1, "image", "https://cdn.example.com/eds-electric-logo.jpg",
                                      alt="Ed's Electric logo")
    masthead = legacy.PreparedMedia(2, "image", "https://cdn.example.com/creativebloq-site-logo.jpg",
                                    alt="Creative Bloq website logo")
    assert not legacy._hard_reject(legitimate, marketing_context=True,
                                  story_title="Ed's Electric logo design",
                                  story_text="Ed's Electric logo designed by Josiah Jost")
    assert legacy._hard_reject(masthead, marketing_context=True,
                               story_title="Ed's Electric logo design",
                               story_text="Ed's Electric logo designed by Josiah Jost")
    assert legacy._hard_reject(legitimate, story_title="New robot chip launched")


def test_238_nontopic_campaign_gallery_retains_all_source_art():
    a = [SimpleNamespace(kind="image", url=f"https://cdn.test/visual-{i}.jpg") for i in range(4)]
    output, dropped = choose_identity_story_media_238(
        a, title="Colourful campaign posters take over London",
        raw_text="A design campaign shows four new posters", source_kind="web",
    )
    assert output == a and dropped == 0


def test_238_explicit_schema_logo_gallery_retains_all_assets():
    title = "New logo and rebranding of Ed's Electric"
    items = [SimpleNamespace(kind="image", url=f"https://cdn.test/eds-electric-{i}.jpg",
                             alt="Ed's Electric", caption="", gallery=True,
                             schema_verified=True, page_declared=True, featured=False, context="")
             for i in range(3)]
    output, dropped = choose_identity_story_media_238(items, title=title,
                    raw_text="Ed's Electric released three identity variations", source_kind="web")
    assert output == items and dropped == 0


def test_238_telegram_album_of_logo_untouched():
    items = [SimpleNamespace(kind="image", url=f"https://cdn.test/{i}.jpg") for i in range(3)]
    output, dropped = choose_identity_story_media_238(items, title="New logo for school",
                                                       raw_text="New logo", source_kind="telegram")
    assert output == items and dropped == 0
