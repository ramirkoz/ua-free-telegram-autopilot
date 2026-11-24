"""2.3.54: operator 24-Nov acceptance of 21 LIVE stories and rejection of four.

No operator SQLite, credentials, Telegram, external network, or old receipts are
included or mutated by these tests. The complete actual-source cohort is also
checked read-only against the user's own Data export during release QA.
"""
from __future__ import annotations

import json

from telegram_autopilot.v2.editorial_owner_2354 import (
    owner_source_veto_2354,
    story_needs_embedded_video_2354,
    video_story_media_reason_2354,
)
from telegram_autopilot.v2.editorial_blueprint_250 import build_editorial_blueprint
from telegram_autopilot.v2.editorial_voice_2337 import newsroom_voice_2337


def article(title: str, raw: str, media=None, *, links=()):
    return {
        "title": title,
        "raw_text": raw,
        "media_json": json.dumps(media or []),
        "article_layout_json": json.dumps({"video_links": list(links)}),
    }


def test_1418_ordinary_price_cut_is_rejected():
    a = article(
        "Five-in-one microwave is getting a $130 price cut before Thanksgiving",
        "The five functions include an air fryer. Click Here to Buy Now: "
        "$349.99 $479.99 (27% off). Launched in April 2025.",
    )
    assert owner_source_veto_2354("creative", a) == "CREATIVE_ROUTINE_DISCOUNT_ONLY_2354"


def test_1414_ordinary_costco_style_prepared_sides_are_rejected_without_brand_blacklist():
    a = article(
        "Store Brought Back 2 Pre-Made Sides Just In Time For The Holidays (But Only One Is Worth Your Money)",
        "The prepared foods section has mashed potatoes and lobster mac and cheese. "
        "Customers say only one side is worth buying for holiday cooking.",
    )
    assert owner_source_veto_2354("creative", a) == "CREATIVE_ORDINARY_RETAIL_FOOD_2354"
    innovative = article(
        "A fried chicken disc replaces the missing GTA 6 video game disc",
        "The brand made an edible novelty fried-chicken disc with game packaging. "
        "Fans bring their game cases to receive the promotional design.",
    )
    assert not owner_source_veto_2354("creative", innovative)


def test_2186_obituary_is_not_disguised_as_science_news():
    a = article(
        "Vale, Chris Example: Australian science grieves the loss of an ecologist",
        "Australia has lost a distinguished ecologist. His achievements and legacy are vast. "
        "He died on November 17; his team studied animals in the desert.",
    )
    assert owner_source_veto_2354("science", a) == "SCIENCE_OBITUARY_WITHOUT_NEW_RESULT_2354"
    actual_discovery = article(
        "Ecologists discover why desert predators keep prey populations balanced",
        "A newly published experiment found how different predators affect the local ecosystem.",
    )
    assert not owner_source_veto_2354("science", actual_discovery)


def test_1416_cinematic_ad_requires_actual_video_not_website_embedded_link():
    title = "Creative KFC campaign puts a saucy twist on Indian cinematic storytelling"
    source = (
        "KFC India has released a new campaign film titled Drip Happens. "
        "Directed by Bruno Bossi, the film centres around a matchmaking meeting. "
        "The bride's aunt does not approve of the groom and the scene gets chaotic."
    )
    youtube = ["https://www.youtube.com/watch?v=YDaAgeyVXiw"]
    poster = ["https://example.org/poster.jpg"]
    a = article(title, source, poster, links=youtube)
    assert story_needs_embedded_video_2354("creative", a)
    assert video_story_media_reason_2354("creative", a) == "CREATIVE_FILM_VIDEO_ASSET_REQUIRED_2354"
    assert owner_source_veto_2354("creative", a) == "CREATIVE_FILM_VIDEO_ASSET_REQUIRED_2354"
    playable = article(title, source, ["video|https://example.org/brand-campaign.mp4"], links=youtube)
    assert video_story_media_reason_2354("creative", playable) == ""
    assert owner_source_veto_2354("creative", playable) == ""
    assert build_editorial_blueprint(playable, commercial=True).kind == "commercial_filmed_story"


def test_positive_design_and_viral_stunt_need_no_video_by_default():
    rows = [
        ("A Chinese brand drove its car off a cliff to demonstrate safety",
         "The crash test stunt happened in a video; the vehicle landed nose-first and turned over. A brand promotion.", []),
        ("KFC offers a fried chicken GTA 6 replacement disc",
         "KFC Spain designed the replacement disc and its game case packaging as an unusual promotion.", []),
        ("Design studio introduces a smaller handcrafted pendant lamp",
         "The birch shade uses bent wooden slats and creates a new sculptural silhouette.", []),
        ("Tomb festival holds qualifying tyrannosaurus race",
         "A novelty costume race brought visitors to a cultural festival in Osaka.", []),
        ("Film director jokes that a game was cancelled after seeing GTA 6",
         "An unusually funny remark from a game director about a rival game.", []),
        ("Humans will go backwards in time, a futurist forecasts",
         "A scientist's bold projection on future longevity is a theory, not experimental proof.", []),
    ]
    for title, source, media in rows:
        role = "science" if "futurist" in title else "creative"
        assert owner_source_veto_2354(role, article(title, source, media)) == "", title


def test_2354_voice_preserves_source_and_rejects_shot_by_shot_description():
    creative = newsroom_voice_2337(commercial=True, final=True)
    science = newsroom_voice_2337(science=True, final=True)
    region = newsroom_voice_2337(monitoring=True, final=True)
    assert "текстова аудіодескрипція" in creative
    assert "Точність і редакторський сенс" in science
    assert "У тексті має" in region
