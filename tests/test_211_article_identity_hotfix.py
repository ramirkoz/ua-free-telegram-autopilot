"""P0: campaign article/source binding and unrelated marketing imagery."""
from telegram_autopilot.collector import _article_title_identity, _enrich_article
from telegram_autopilot.models import CollectedArticle
from telegram_autopilot import collector
from telegram_autopilot.media_pipeline import _layout_items


def test_happy_meal_cannot_bind_euroleague_source():
    assert not _article_title_identity(
        "McDonald's uses Happy Meal boxes to screen children's eyesight",
        "What does an official sponsor really sponsor? EuroLeague PPC"
    )


def test_oslo_article_cannot_bind_dolly_parton_source():
    assert not _article_title_identity(
        "Visit Oslo turns its famous grump into a Christmas musical",
        "Dolly Parton stars in new advertising campaign"
    )


def test_same_story_title_has_common_anchors():
    assert _article_title_identity(
        "Visit Oslo turns its famous grump into a Christmas musical",
        "Visit Oslo turns its famous grump into a Christmas musical | Famous Campaigns",
    )


def test_wrong_resolved_page_is_rejected_even_if_it_has_images(monkeypatch):
    class Resp:
        body = b"<html>not the desired story</html>"
    class Extracted:
        text = "Sponsored basketball campaign. " * 40
        title = "What does an official sponsor really sponsor?"
        media_urls = ["https://shots.net/euroleague-bus.jpg"]
        layout_json = '{"featured":"https://shots.net/euroleague-bus.jpg"}'
    monkeypatch.setattr(collector, "_source_fetch", lambda *a, **k: Resp())
    monkeypatch.setattr(collector, "extract_article_content", lambda *a, **k: Extracted())
    item = CollectedArticle("id", "McDonalds Happy Meal eye tests for children",
                            "https://shots.net/news/view/what-does-an-official-sponsor-really-sponsor",
                            "Original Happy Meal story", None, ["https://shots.net/feed-image.jpg"])
    result = _enrich_article(item)
    assert result.raw_text == "Original Happy Meal story"
    assert result.media_urls == []
    assert '"MISMATCH"' in result.article_layout_json


def test_scoped_article_body_disallows_unrelated_rss_fallback():
    import json
    layout = json.dumps({"blocks":[{"type":"media","kind":"image","index":1,"position":0.1,
        "url":"https://example.com/oslo-photo.jpg","schema_verified":True,"gallery":True}]})
    hero, body = _layout_items(layout, ["https://example.com/dolly-parton.jpg"])
    assert [x.url for x in body] == ["https://example.com/oslo-photo.jpg"]
