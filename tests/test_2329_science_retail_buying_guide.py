"""v2.3.29: verified CTRL+UA #1857 retail guide must not reach AI or Telegram."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, ChannelPolicy, DedupeProfile,
    EditorialRuntimeProfile, Decision,
)
from telegram_autopilot.v2.editorial import EditorialEngine, hard_editorial_reject
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_source_topic_2319 import (
    editorial_source_topic_reason_2319,
    science_retail_buying_guide_reason_2329,
)

SOURCE_97242 = {
    "id": 97242,
    "title": "The 6 Best Electric Snowblowers Are Plenty Powerful—and Quieter Alternatives to Gas Models",
    "raw_text": (
        "Gear-obsessed editors choose every product we review. "
        "We may earn commission if you buy from a link. Why Trust Us? "
        "Best Electric Snowblowers. How We Selected. What to Consider. "
        "Best Overall: Ryobi 40-Volt 24-Inch Two-Stage Snow Blower. "
        "Best Value Two-Stage: Ego Power+ 24-Inch Two-Stage Snow Blower. "
        "Best Budget: Snow Joe 24-Volt 18-Inch Snow Blower. "
        "Our selections for this list are based on years of testing."
    ),
    "source_url": "https://www.popularmechanics.com/home/lawn-garden/a38146316/best-electric-snow-blowers/",
}


def _science():
    return ChannelConfig(
        id=1, name="CTRL+UA", telegram_chat_id="-1001",
        mode=ChannelMode.EDITORIAL,
        editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
        dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
        dedupe_scientific_names=True, dedupe_compound_events=True,
        policy=ChannelPolicy(
            channel_id=1,
            selection_rules=MARKER + " Science technology for general readers."
        ),
    )


def _creative():
    channel = _science()
    channel.editorial_runtime_profile = EditorialRuntimeProfile.COMMERCIAL_EDITORIAL
    return channel


def test_2329_real_1857_fails_source_only_and_prepublish():
    assert science_retail_buying_guide_reason_2329(SOURCE_97242) == "SCIENCE_RETAIL_BUYING_GUIDE_2329"
    assert editorial_source_topic_reason_2319(_science(), SOURCE_97242) == "SCIENCE_RETAIL_BUYING_GUIDE_2329"
    assert hard_editorial_reject(_science(), SOURCE_97242, "Гарний список шести електричних моделей.") == "SCIENCE_RETAIL_BUYING_GUIDE_2329"


def test_2329_veto_before_ai_calls():
    engine = EditorialEngine.__new__(EditorialEngine)
    engine.gateway = SimpleNamespace(run=lambda *a, **kw: pytest.fail("no AI call allowed"))
    engine.learning = SimpleNamespace(topic_assessment=lambda *a, **kw: pytest.fail("no topic learning call allowed"))
    result = engine._select_editorial(_science(), SOURCE_97242)
    assert result.decision == Decision.REJECT
    assert result.reason == "SCIENCE_RETAIL_BUYING_GUIDE_2329"


@pytest.mark.parametrize("title,body", [
    ("New battery chemistry allows electric snowblowers to work in freezing conditions",
     "Scientists demonstrate a novel electrolyte in testing; this is a real new invention."),
    ("Engineers demonstrate a new robot for automated snow clearance",
     "A university laboratory has developed and tested a new robot, documenting its engineering design."),
    ("Testing reveals why heat pumps lose efficiency in heavy snow",
     "The research team measured the results in controlled field experiments."),
    ("The 6 Best Electric Snowblowers Reviewed as a New Battery Prototype Emerges",
     "Engineering researchers report a new experimental chemistry validated in their laboratory."),
    ("The 5 Best AI Techniques for Diagnosing Disease in Clinical Trials",
     "Researchers compared five experimental methods and reported trial outcomes."),
]):
def test_2329_never_blocks_discovery_by_headline_alone(title, body):
    article = {"title": title, "raw_text": body}
    assert science_retail_buying_guide_reason_2329(article) == ""
    assert editorial_source_topic_reason_2319(_science(), article) == ""


@pytest.mark.parametrize("title,body", [
    ("The 8 Best Cordless Drills for Your Workshop",
     "We may earn commission if you buy from a link. Best Overall: Model X. How We Selected."),
    ("Top 5 Robot Vacuum Cleaners for Apartments",
     "Our picks include Best Budget: Model A and Best Value: Model B. We may earn commissions."),
    ("Best Electric Lawn Mowers to Buy in 2026",
     "Best Overall: Model A. Best Budget: Model B. What to Consider before buying."),
]):
def test_2329_other_true_buying_guides_vetoed(title,body):
    assert science_retail_buying_guide_reason_2329({"title": title, "raw_text": body}) == "SCIENCE_RETAIL_BUYING_GUIDE_2329"


def test_2329_veto_is_scoped_to_science():
    assert editorial_source_topic_reason_2319(_creative(), SOURCE_97242) == ""
    assert editorial_source_topic_reason_2319(
        ChannelConfig(id=3,name="GR",telegram_chat_id="-1003",mode=ChannelMode.MONITORING), SOURCE_97242
    ) == ""


def test_2329_does_not_block_retail_title_without_two_independent_body_signals():
    article={"title":"The 6 Best New AI Chips Tested by University Engineers",
             "raw_text":"Research team ran a new comparison with quantified power efficiency results. "
                        "Best Overall was mentioned in one unrelated quote."}
    assert science_retail_buying_guide_reason_2329(article) == ""
