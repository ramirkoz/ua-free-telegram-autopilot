"""2.3.35 owner color-label preference controls (no private XLSX or live DB).

Tests exercise the shared selection/READY safety gate, not only a helper.
All positive controls remain subject to independent fact, media, TTL,
provenance, deduplication and Telegram UNKNOWN controls.
"""
from __future__ import annotations

import pytest

from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, ChannelPolicy, DedupeProfile,
    EditorialRuntimeProfile, Decision,
)
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.editorial_owner_235 import (
    owner_source_veto_235, SCIENCE_GUIDANCE_235, CREATIVE_GUIDANCE_235,
    REGIONAL_GUIDANCE_235,
)
from telegram_autopilot.v2.editorial import EditorialEngine, hard_editorial_reject
from telegram_autopilot.v2.editorial_second_opinion_2320 import eligible_second_opinion_2320
from telegram_autopilot.v2.editorial_owner_2332 import monitoring_source_reason_2332

SCI = ChannelConfig(id=1, name="CTRL", telegram_chat_id="-1001", mode=ChannelMode.EDITORIAL,
                    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
                    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
                    dedupe_scientific_names=True,dedupe_compound_events=True,
                    policy=ChannelPolicy(channel_id=1,selection_rules=MARKER+" наука"))
CRE = ChannelConfig(id=2,name="ПРОДАНО!",telegram_chat_id="-1002",mode=ChannelMode.EDITORIAL,
                    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
                    policy=ChannelPolicy(channel_id=2,selection_rules=MARKER+" креатив"))


@pytest.mark.parametrize("post,reason", [
    ({"title":"5 Powerful PC Tools That Can Help Diagnose Problems",
      "raw_text":"Desktop PC support problems can be fixed using maintenance utilities. The tutorial lists diagnostic tools to find and repair common issues."},
     "SCIENCE_ORDINARY_PC_DIAGNOSTIC_ROUNDUP_235"),
    ({"title":"If Your Roku TV Keeps Reading Everything Out-Loud, Try This",
      "raw_text":"The Roku voice screen reader can be turned off from accessibility settings. A user can follow these menus to stop reading everything aloud."},
     "SCIENCE_ROKU_VOICE_HOWTO_235"),
    ({"title":"5 tips to extend laptop battery life",
      "raw_text":"Try changing laptop settings for battery efficiency. The article shows which menus to use."},
     "SCIENCE_ROUTINE_BATTERY_TIPS_235"),
    ({"title":"Apple CarPlay speed camera warnings: how to turn them on",
      "raw_text":"Go to the car settings and enable alerts. The guide lists every tap on the phone."},
     "SCIENCE_CARPLAY_SETTINGS_NOT_NEWS_235"),
])
def test_source_and_old_ready_owner_red_science_rejected(post,reason):
    assert editorial_source_topic_reason_2319(SCI,post)==reason
    assert hard_editorial_reject(SCI,post,"Old READY story") == reason
    ed=object.__new__(EditorialEngine)
    assert ed.select(SCI,post).decision == Decision.REJECT


def test_owner_red_generic_gift_list_requires_shopping_copy():
    post={"title":"5 Thoughtful Gifts for Men Who Appreciate Great Design",
          "raw_text":"This gift guide lists our shopping picks and where to buy. Choose from many best-selling products."}
    assert editorial_source_topic_reason_2319(CRE,post)=="CREATIVE_GENERIC_GIFT_SHOPPING_LIST_235"
    original_design={"title":"Five thoughtful gifts that are original design objects",
                     "raw_text":"Five original designers make new objects for a museum exhibit. The works show a new folding mechanism."}
    assert editorial_source_topic_reason_2319(CRE,original_design)==""


@pytest.mark.parametrize("role,title,body", [
    ("science","New study uses PC diagnostics to predict hardware failures",
     "Researchers designed a new statistical model. The new research was verified on real laptop faults."),
    ("science","How the new Gemini model changes multimodal inference",
     "Researchers released technical results showing a new multimodal capability. The source documents measured results."),
    ("science","Researchers discover novel biodegradable plastic",
     "A team demonstrated a new material that survives dishwashers. They measured the time needed for degradation in natural conditions."),
    ("science","New Roku screen reader designed for accessibility",
     "New research into navigation accessibility supports improved text-to-speech. Engineers validated a novel UI capability."),
    ("creative","66 real breakup stories shared by women",
     "Several women discuss real breakup experiences and how their lives changed. The reporting interviews people about relationships."),
    ("creative","Scientists discover a surprising bond between a donkey and a bull",
     "A documented rare animal pairing surprised a team of researchers. The team describes its factual observations in the original study."),
    ("creative","Artists showcase original illustrations from daily life",
     "An illustrator created an original series documenting strange moments. The art uses a distinctive visual approach."),
    ("creative","Designer makes an inventive new multifunctional table",
     "An original construction transforms an ordinary object into two pieces of furniture. The design can be physically folded."),
])
def test_owner_positive_subjects_are_not_vetoed_by_235(role,title,body):
    article={"title":title,"raw_text":body}
    channel=SCI if role=="science" else CRE
    assert owner_source_veto_235(role,article)==""
    assert editorial_source_topic_reason_2319(channel,article)==""


def test_creative_second_opinion_considers_relationships_with_source_proof():
    article={"title":"Unexpected breakup stories reveal relationship psychology",
             "raw_text":"A researcher documented 66 personal stories about breakups and romantic relationships. "*5}
    assert eligible_second_opinion_2320(article,"creative")


def test_owner_guidance_is_role_scoped_and_not_a_security_exception():
    assert "412 ТАК" in SCIENCE_GUIDANCE_235
    assert "253 ТАК" in CREATIVE_GUIDANCE_235
    assert "1075 ТАК" in REGIONAL_GUIDANCE_235
    assert "ROI" not in SCIENCE_GUIDANCE_235
    assert "НЕ" in CREATIVE_GUIDANCE_235
    assert "NO ANNOUNCEMENTS" in REGIONAL_GUIDANCE_235


def test_monitoring_explicit_hard_announcement_policy_still_applies():
    post={"title":"17 листопада у Запоріжжі відбудеться поховання захисника",
          "raw_text":"17 листопада у Запоріжжі відбудеться поховання військовослужбовця. Місто повідомило місце церемонії."}
    assert monitoring_source_reason_2332(post)=="MONITORING_FUTURE_FUNERAL_NOTICE_2333"


@pytest.mark.parametrize("title", [
    "55 People Who Signed NDAs Reveal Just Enough To Leave You Desperately Curious About All The Rest",
    "79 Random Memes That Have No Business Being This Relatable",
    "40 Nostalgic-Looking Photos Shared By Photographers On Threads",
    "55 Divorce Lawyers Share Dirty Secrets About Couples That Had No Business Being This Messy",
    "64 Nightmare Guests Who Made Themselves Way Too Comfortable In Someone Else's Home",
])
def test_owner_red_numbered_social_roundups_never_reach_publish(title):
    post={"title":title,"raw_text":"The source includes numbered anonymous social media submissions, photos, memes or opinions."}
    reason="CREATIVE_ENUMERATED_SOCIAL_ROUNDUP_OWNER_RED_235"
    assert editorial_source_topic_reason_2319(CRE, post)==reason
    assert hard_editorial_reject(CRE, post, "Old READY story") == reason
    ed=object.__new__(EditorialEngine)
    assert ed.select(CRE,post).decision == Decision.REJECT


@pytest.mark.parametrize("title", [
    "66 Women Share The Final Straw That Made Staying With Him No Longer An Option",
    "66 real breakup stories shared by women",
    "The 1839 Awards Announce Winners of Photographer of the Year (39 Pics)",
    "39 artists win an international photography competition",
])
def test_owner_positive_66_women_and_award_report_not_genre_blocked(title):
    post={"title":title,"raw_text":"Original source with article text and independent reviewable facts, subject to subsequent editorial and fact QA."}
    assert owner_source_veto_235("creative", post)==""
