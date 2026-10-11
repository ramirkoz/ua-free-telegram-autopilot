import json
from types import SimpleNamespace

import pytest

from telegram_autopilot import media_pipeline
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


def test_five_web_stories_reject_reused_site_ad_and_keep_five_heroes(monkeypatch):
    def probe(item, **kwargs):
        item.data = b"validated-image"
        item.width, item.height = 1200, 675
        item.mime_type = "image/jpeg"
        return item

    monkeypatch.setattr(media_pipeline, "_probe_image", probe)
    ad = "https://cdn.publisher.test/house-ad-cpu-socket.jpg"
    titles = [
        "Kingchaser 3D printed aircraft",
        "Yandex Kaluga datacenter attack",
        "AnyPS5 graphics shader milestone",
        "Free Steam AI game daily expense",
        "PS5SX2 PS2 emulator homebrew",
    ]
    output_urls = []
    for i, title in enumerate(titles):
        tokens = "-".join(title.casefold().split())
        good = f"https://cdn.publisher.test/{tokens}.jpg"
        layout = json.dumps({
            "featured": "image|" + ad,
            "featured_meta": {"provenance": "page_hero", "alt": "generic CPU image"},
            "blocks": [
                {"type": "media", "kind": "image", "url": good,
                 "alt": title, "caption": title, "position": 0.04,
                 "context": "article story visual"}
            ],
        })
        article = {
            "id": 100 + i, "title": title, "raw_text": title + " released today.",
            "final_text": "Unrelated AI text mentions computer motherboard.",
            "media_json": json.dumps([ad, good]), "article_layout_json": layout
        }
        channel = SimpleNamespace(
            mode=ChannelMode.EDITORIAL, editorial_runtime_profile="standard"
        )
        bundle = build_publication_media_bundle(channel, article, excluded_urls={ad})
        assert ad not in [x.url for x in bundle.items]
        assert good in [x.url for x in bundle.items]
        output_urls.append(good)
    assert len(set(output_urls)) == 5


def test_og_image_is_untrusted_page_hint_not_verified_story_hero():
    featured, _ = media_pipeline._layout_items(
        json.dumps({
            "featured": "image|https://cdn.example.com/house-ad.jpg",
            "featured_meta": {"provenance": "verified_og", "alt": "CPU socket"}
        }), []
    )
    assert featured is not None
    assert featured.context == "open_graph_hint"
    assert not media_pipeline._semantic_media_match(
        featured, title="New plant gene editing treatment",
        article_text="Researchers publish a plant biology study.",
    )


def test_same_dated_mourning_decision_suppressed_across_sources():
    older = {
        "title": "11 жовтня у Запоріжжі оголошено День жалоби",
        "raw_text": "11 жовтня у Запоріжжі — День жалоби. Міська влада повідомила про рішення.",
        "source_id": 10,
    }
    repeated = {
        "title": "11 жовтня у Запоріжжі День жалоби",
        "raw_text": "11 жовтня у Запоріжжі оголошено День жалоби.",
        "source_id": 11,
    }
    same, reason = event_fingerprint_same_event(older, repeated)
    assert same, reason


def test_different_city_mourning_not_duplicate():
    older = {"title": "11 жовтня у Запоріжжі День жалоби",
             "raw_text": "11 жовтня у Запоріжжі День жалоби", "source_id": 1}
    other = {"title": "11 жовтня у Києві День жалоби",
             "raw_text": "11 жовтня у Києві День жалоби", "source_id": 2}
    same, _ = event_fingerprint_same_event(older, other)
    assert not same
