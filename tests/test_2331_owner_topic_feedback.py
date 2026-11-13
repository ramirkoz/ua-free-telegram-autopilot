"""13.11.2026 owner feedback: decline meme lists and consumer how-to posts.

No network, AI calls, Telegram publishing, or operator Data mutations.
Newer operator preference overrides six older science tutorial positive labels.
"""
import pytest
from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, ChannelPolicy, DedupeProfile,
    EditorialRuntimeProfile, Decision,
)
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.editorial import EditorialEngine, hard_editorial_reject

SCIENCE = ChannelConfig(
    id=1, name="Science", telegram_chat_id="-1001", mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True, dedupe_compound_events=True,
    policy=ChannelPolicy(channel_id=1, selection_rules=MARKER + " наука"),
)
CREATIVE = ChannelConfig(
    id=2, name="Creative", telegram_chat_id="-1002", mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    policy=ChannelPolicy(channel_id=2, selection_rules=MARKER + " дизайн"),
)

@pytest.mark.parametrize("channel,post,reason", [
    (SCIENCE, {
        "title": "Google Maps Has A Built-In Function For Measuring Your Yard - Here's How To Use It",
        "raw_text": "Open Google Maps and right-click a yard on the map. Select Measure distance and click another point. This is a consumer how-to tutorial.",
    }, "SCIENCE_CONSUMER_HOWTO_NOT_NEWS_2331"),
    (SCIENCE, {
        "title": "5 Clever Uses For Siri AI In Your iPhone Camera App",
        "raw_text": "Use the iPhone camera with Siri AI to scan notes and identify plants. The article lists ordinary tricks and instructions.",
    }, "SCIENCE_CONSUMER_HOWTO_NOT_NEWS_2331"),
    (SCIENCE, {
        "title": "How to use Gboard to boost productivity on your Android phone",
        "raw_text": "Gboard's keyboard settings are described. The reader is instructed how to enable the existing consumer features.",
    }, "SCIENCE_CONSUMER_HOWTO_NOT_NEWS_2331"),
    (CREATIVE, {
        "title": "61 Random Memes That Are Equal Parts Relatable, Ridiculous, And Hilarious",
        "raw_text": "#1\n#2\n#3\n#4\nGeneric recycled jokes without original creators, a campaign or new event. The list provides numbered images and no original creative achievement.",
    }, "CREATIVE_GENERIC_MEME_ROUNDUP_2331"),
])
def test_owner_rejections_work_before_ai_and_at_ready_publish(channel, post, reason):
    assert editorial_source_topic_reason_2319(channel, post) == reason
    assert hard_editorial_reject(channel, post, "Already prepared READY text") == reason
    outcome = object.__new__(EditorialEngine).select(channel, post)
    assert outcome.decision == Decision.REJECT
    assert outcome.reason == reason


@pytest.mark.parametrize("channel,post", [
    (SCIENCE, {
        "title": "New Siri AI camera mode launches with tested object recognition",
        "raw_text": "Researchers measured 3000 recognition samples and announced a new vision breakthrough. The full study documents experimental results.",
    }),
    (SCIENCE, {
        "title": "Researchers discover a new way to detect exoplanets with a telescope",
        "raw_text": "Researchers measured a new planetary signal and published telescope observations. The result has been independently replicated.",
    }),
    (SCIENCE, {
        "title": "How to run open AI models in production without owning the serving stack",
        "raw_text": "Engineers describe new model serving architecture and measured performance. This is a developer platform overview rather than phone settings.",
    }),
    (CREATIVE, {
        "title": "The 5 Best Cabin Designs of November 2026",
        "raw_text": "Five original architectural projects from named creators have unique materials and functional ideas. Each includes an actual new built design.",
    }),
    (CREATIVE, {
        "title": "8 Best Desk Accessories of October 2026 to Upgrade Your Workspace",
        "raw_text": "Original objects by named designers have distinctive materials and mechanisms. This is about genuine creative work, not unrelated recycled memes.",
    }),
    (CREATIVE, {
        "title": "Artists create a viral satirical meme campaign with original animation",
        "raw_text": "A studio produced an original art campaign with animation. This is a new creative work and not a numbered slideshow.",
    }),
])
def test_all_other_recent_topics_stay_eligible(channel, post):
    assert editorial_source_topic_reason_2319(channel, post) == ""
