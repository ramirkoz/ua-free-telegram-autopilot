"""Owner RED 19 Nov: mundane repairs, gift/sauce/meme compilations are not news."""
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_owner_2344 import owner_reader_value_reason_2344
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.editorial import hard_editorial_reject

SCIENCE = SimpleNamespace(
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True,
    dedupe_compound_events=True,
    policy=SimpleNamespace(selection_rules=MARKER),
)
CREATIVE = SimpleNamespace(
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    policy=SimpleNamespace(selection_rules=MARKER),
)

GIFT_106538 = {
    "title": "8 Japanese Gifts for Men She’ll Love Giving and He’ll Use Every Day",
    "raw_text": "These eight picks focus on Japanese designs with a specific job. "
                "1. Sony ELF-MN1\n2. Eiger 8-in-1 Scissors\n3. Panasonic Shaver\n"
                "What we like: easy use. What we dislike: cost.",
}
GIFT_99357 = {
    "title": "5 Thoughtful Gifts for Men Who Appreciate Great Design",
    "raw_text": "These five gifts include drinkware, lighting and coffee items. "
                "Buy a tasteful present for the man who appreciates everyday objects.",
}
MEMES_98745 = {
    "title": "61 Random Memes That Are Equal Parts Relatable, Ridiculous, And Hilarious",
    "raw_text": "#1\n#2\n#3\nThese memes are a collection of hilarious moments.",
}
SAUCE_103186 = {
    "title": "Every Taco Bell Sauce And Dip, Ranked From Worst To Best",
    "raw_text": "Taco Bell sauces and dips come in a range of flavors. We taste-tested "
                "them all to find out which is the best.",
}
REPAIR_94051 = {
    "title": "Saving a Vintage High-Voltage Power Supply From the Scrap Heap",
    "raw_text": "An old Fluke power supply was restored using an isolated transformer "
                "and a variac. The circuit and capacitors needed replacing.",
}

def test_japanese_gift_list_blocked_at_source_and_ready_prepublish():
    reason = "CREATIVE_GIFT_ROUNDUP_NOT_NEWS_2344"
    assert owner_reader_value_reason_2344("creative", GIFT_106538) == reason
    assert editorial_source_topic_reason_2319(CREATIVE, GIFT_106538) == reason
    assert hard_editorial_reject(CREATIVE, GIFT_106538, "Японські подарунки...") == reason

def test_previous_gift_list_and_further_variants_rejected():
    assert owner_reader_value_reason_2344("creative", GIFT_99357) == "CREATIVE_GIFT_ROUNDUP_NOT_NEWS_2344"
    assert owner_reader_value_reason_2344("creative", dict(GIFT_106538, title="9 Gifts for Collectors Under $50"))

def test_meme_and_sauce_lists_rejected():
    assert owner_reader_value_reason_2344("creative", MEMES_98745) == "CREATIVE_MEME_COMPILATION_NOT_NEWS_2344"
    assert owner_reader_value_reason_2344("creative", SAUCE_103186) == "CREATIVE_SAUCE_RANKING_NOT_NEWS_2344"
    assert owner_reader_value_reason_2344("creative", {
        "title": "Walmart's Great Value Vs Ocean Spray: Who Makes The Better Cranberry Sauce",
        "raw_text": "Grocery product comparison tested these competing brands.",
    }) == "CREATIVE_SAUCE_RANKING_NOT_NEWS_2344"

def test_vintage_repair_is_not_technology_news():
    assert owner_reader_value_reason_2344("science", REPAIR_94051) == "EDITORIAL_MUNDANE_REPAIR_NOT_NEWS_2344"
    assert editorial_source_topic_reason_2319(SCIENCE, REPAIR_94051) == "EDITORIAL_MUNDANE_REPAIR_NOT_NEWS_2344"

def test_medical_material_and_science_institution_are_not_repair_tutorials():
    assert owner_reader_value_reason_2344("science", {
        "title": "FDA Approves First-of-Its-Kind Bone Repair Material Made From Pearl Shells",
        "raw_text": "New medical material wins FDA clearance after years of scientific research.",
    }) == ""
    assert owner_reader_value_reason_2344("science", {
        "title": "American science is broken. Meet the people fixing it",
        "raw_text": "Scientists reopen climate data dashboards after federal staffing cuts.",
    }) == ""

def test_preserve_right_to_repair_policy_and_authentic_inventions():
    assert owner_reader_value_reason_2344("science", {
        "title": "Court orders right-to-repair protections for smartphone owners",
        "raw_text": "The regulator orders a mandatory repairability disclosure.",
    }) == ""
    for row in (
        {"title": "Aurzen ZIP Pro Puts a Foldable Projector and Basquiat Art on Your Holiday Gift List",
         "raw_text": "A projector folds into a compact block and ships in a newly designed special edition."},
        {"title": "Seth Rogen Checks Off His Gift List in Sephora’s Holiday Campaign",
         "raw_text": "Sephora premieres an original filmed holiday advertising campaign."},
        {"title": "Neri Oxman experiments with fabric pigment created by bacteria",
         "raw_text": "Designer Neri Oxman develops a new living textile dye technology."},
    ):
        assert owner_reader_value_reason_2344("creative", row) == ""

def test_meme_collections_in_non_leading_title_and_monitoring_untouched():
    assert owner_reader_value_reason_2344("creative", {
        "title": "From Airline Deals To Presidential Jokes, 20 Memes Made The Embassy Go Viral",
        "raw_text": "A retrospective of twenty memes followed the news.",
    }) == "CREATIVE_MEME_COMPILATION_NOT_NEWS_2344"
    assert owner_reader_value_reason_2344("monitoring", GIFT_106538) == ""
    assert owner_reader_value_reason_2344("creative", {"title": GIFT_106538["title"], "raw_text": ""}) == ""
