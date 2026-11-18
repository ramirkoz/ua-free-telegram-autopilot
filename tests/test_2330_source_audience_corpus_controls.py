"""v2.3.30 source vetoes distilled from 1472 authentic owner choices.

Fixtures are neutral source excerpts only. Full owner corpus stays private;
code is evaluated against its complete original RAW SQLite in READ-ONLY mode.
"""
from telegram_autopilot.v2.editorial_audience_2330 import editorial_audience_source_reason_2330


def test_2330_rejects_unambiguous_science_coupon_sale_not_new_technology():
    cases = [
        ("The laptop is on Sale for $499", "A retailer has discounted the laptop; buy now and save."),
        ("Best Early Black Friday Deals on Electronics", "Our deals on consumer laptops are available during the sale."),
        ("Coupon Codes: 40% Off", "Save on purchases by using a coupon at checkout."),
    ]
    for title, body in cases:
        assert editorial_audience_source_reason_2330(
            "science", {"title": title, "raw_text": body}
        ) == "SCIENCE_RETAIL_PROMOTION_2330"


def test_2330_science_genuine_industrial_deal_stays_eligible():
    # A business "deal" is not necessarily a shopping promotion.
    assert editorial_audience_source_reason_2330("science", {
        "title": "Researchers announce a new gas-turbine system in an energy deal",
        "raw_text": "The company signed a technology partnership to test a new power system.",
    }) == ""


def test_2330_creative_personnel_ad_not_a_campaign_idea():
    cases = [
        ("Agency appoints new Managing Director", "The advertising agency announces the appointment and management team."),
        ("Creative directors depart studio", "Two agency executives have departed after leadership changes."),
        ("Brand names new advertising agency", "The business selected a new marketing partner following an agency pitch."),
    ]
    for title, body in cases:
        assert editorial_audience_source_reason_2330(
            "creative", {"title": title, "raw_text": body}
        ) == "CREATIVE_AGENCY_PERSONNEL_PR_2330"


def test_2330_creative_original_ad_campaign_not_blocked_by_brand():
    assert editorial_audience_source_reason_2330("creative", {
        "title": "A studio's inventive animated campaign becomes an installation",
        "raw_text": "The agency appointed an illustrator to build original animated public art.",
    }) == ""


def test_2330_creative_direct_coupon_offer_is_not_creative_story():
    assert editorial_audience_source_reason_2330("creative", {
        "title": "Get 87% off a web builder with this Black Friday code",
        "raw_text": "The discount applies to a shopping offer and coupon at checkout.",
    }) == "CREATIVE_RETAIL_PROMOTION_2330"
