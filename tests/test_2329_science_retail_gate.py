"""Regression for CTRL+UA #1857: 6-snowblower shopping list, not science news.

Operator source excerpt only; no private Data and no external AI/Telegram calls.
"""
import pytest

from telegram_autopilot.v2 import editorial as ed
from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, ChannelPolicy, Decision, DedupeProfile,
    EditorialRuntimeProfile,
)
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319

SCIENCE = ChannelConfig(
    id=1, name="CTRL+UA", telegram_chat_id="-1001111111",
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True,
    dedupe_compound_events=True,
    policy=ChannelPolicy(channel_id=1, selection_rules=MARKER + " наука"),
)
CREATIVE = ChannelConfig(
    id=2, name="ПРОДАНО!", telegram_chat_id="-1002222222",
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    policy=ChannelPolicy(channel_id=2, selection_rules=MARKER + " креатив"),
)
SNOWBLOWERS = {
    "id": 97242,
    "title": "The 6 Best Electric Snowblowers Are Plenty Powerful—and Quieter Alternatives to Gas Models",
    "source_url": "https://www.popularmechanics.com/home/lawn-garden/a38146316/best-electric-snow-blowers/",
    "raw_text": (
        "Gear-obsessed editors choose every product we review. "
        "We may earn commission if you buy from a link. Why Trust Us? "
        "The 6 Best Electric Snowblowers Are Plenty Powerful—and Quieter Alternatives to Gas Models. "
        "Best Electric Snowblowers. How We Selected. Best Two-Stage. What to Consider. "
        "Ahead, we review both two-stage snow blowers and single-stage snow throwers "
        "and recommend models from Toro, Ego, Milwaukee, and more. "
        "Best Overall: Ryobi 40-Volt 24-Inch Two-Stage Snow Blower. "
        "Best Value Two-Stage: Ego Power+ 24-Inch Two-Stage Snow Blower. "
        "Best Budget: Snow Joe 24-Volt 18-Inch Cordless Single-Stage Snow Blower. "
        "How We Selected: Our selections for this list are based on years of testing."
    ),
}

def test_source_only_snowblower_veto_pre_ai_and_direct_selector():
    expected = "SCIENCE_AFFILIATE_BUYING_GUIDE_2329"
    assert editorial_source_topic_reason_2319(SCIENCE, SNOWBLOWERS) == expected
    engine = object.__new__(ed.EditorialEngine)
    result = engine.select(SCIENCE, SNOWBLOWERS)
    assert result.decision == Decision.REJECT and result.reason == expected
    assert engine._select_editorial(SCIENCE, SNOWBLOWERS).reason == expected

def test_old_ready_snowblower_veto_before_telegram():
    assert ed.hard_editorial_reject(SCIENCE, SNOWBLOWERS, "AI rewritten buying guide") == "SCIENCE_AFFILIATE_BUYING_GUIDE_2329"
    assert editorial_source_topic_reason_2319(CREATIVE, SNOWBLOWERS) == ""

@pytest.mark.parametrize("title,source", [
    ("Researchers unveil a new snowblower motor with higher efficiency",
     "Engineers introduced a novel motor. Independent measurements showed higher efficiency."),
    ("Scientists compare six batteries and discover why one lasts longer",
     "Researchers compared six cell chemistries. The study identified a new mechanism."),
    ("The 6 Best Battery Designs from New Research",
     "Engineers proposed six new electrochemical designs. A paper reports lab measurements."),
    ("New robotic snowplow detects pedestrians without cameras",
     "Researchers built a radar prototype. Tests demonstrated pedestrian detection."),
    ("Comparing battery-electric trucks reveals a charging breakthrough",
     "Engineers measured a novel charging architecture. Results appeared in a study."),
    ("The best use of AI in climate research was a new model",
     "Scientists published an original prediction method. Independent evaluation confirmed it."),
])
def test_real_technology_news_remains_eligible(title, source):
    row = {"title": title, "raw_text": source}
    assert editorial_source_topic_reason_2319(SCIENCE, row) == ""
    assert ed.hard_editorial_reject(SCIENCE, row) == ""

@pytest.mark.parametrize("title,source", [
    ("The 8 Best Electric Cars to Buy in 2026",
     "Our picks: Best Overall Tesla, Best Budget Volvo. How We Tested the cars. Shop now."),
    ("Our Best Home Robots of 2026",
     "We may earn commission when you buy. Best Overall Unit A. Best Value Unit B. How We Selected."),
    ("Best Solar Panels to Buy for Your House",
     "We earn affiliate commission if you buy from a link. How We Selected each product."),
])
def test_shop_roundups_are_rejected(title, source):
    assert editorial_source_topic_reason_2319(SCIENCE, {"title":title,"raw_text":source}) == "SCIENCE_AFFILIATE_BUYING_GUIDE_2329"

def test_title_or_footer_alone_not_a_veto():
    assert editorial_source_topic_reason_2319(SCIENCE, {
        "title": "The 6 Best Electric Cars",
        "raw_text": "Engineers compared six novel drivetrains. Findings were published."
    }) == ""
    assert editorial_source_topic_reason_2319(SCIENCE, {
        "title": "Scientists invent a longer-lasting battery",
        "raw_text": "Best Overall, Best Value, How We Selected appear in footer. Researchers tested a new chemistry."
    }) == ""
