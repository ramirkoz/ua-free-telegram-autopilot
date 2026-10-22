"""Operator #74792 Shots: unrelated story cards & gallery fail closed.

2026-10-22 16:30:54 Kyiv; source title not represented by extracted body.
The media pipeline ranked eight images from unrelated story teasers as a gallery.
"""
from __future__ import annotations

from telegram_autopilot.v2.source_integrity import multi_story_page_cards_reason
from telegram_autopilot.v2.editorial import (
    EditorialEngine, hard_editorial_reject, prepublish_quality_issues,
)
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, Decision

TITLE = "Question time? We're getting better at getting it wrong"
RAW = """How the art of film can make the unseen seen
Beast Films director Lawrence Jacomelli considers how cinema can represent the reality of our internal psychological worlds without directly depicting them.
Gen when? We shouldn’t be put in a box until we’re dead
Labels can be helpful, but has the marketing industry relied too much on the homogenous definition of people? Paul Domenet, Creative Strategic Director at Free The Birds, believes so, saying that advertising's reliance on generational distinctions is doing more harm that good.
Hoard, sweet hoard: What IKEA’s Skyrim shelf can teach brands about fandom
When brands try to play in the world of fandom they can often get it wrong, but not IKEA, says Cat Botibol, Managing Director at Studio Secret Cinema, who thinks the furniture brand's foray into Skyrim is a perfect example of playfulness and intelligence.
Nike & Mbappé: Visibility versus distinctiveness
Nike can claim to dominate sports branding with former athletes like Michael Jordan and Wayne Rooney and current stars such as Erling Haaland and Shelly-Ann Fraser-Pryce all brand ambassadors, but, asks Sam Pittman, Creative Director at Butterfly Cannon, with Kylian Mbappé leaving Nike for relative athletic wear upstart On, are times changing, and is visibility as powerful as distinctiveness?"""
FINAL = """Маркетинг любить розкладати людей по коробках: Gen Z, міленіали, бумери. Так простіше: одне повідомлення, один стиль, і здається, що вся група поводиться однаково. Але саме ця зручність заважає побачити реальних людей.

Вік не пояснює, що людина купує, чого боїться, над чим сміється чи які рішення приймає. Усередині одного покоління — різні звички, цінності та способи життя. Коли бренд говорить не з людиною, а з ярликом, він промахується ще до першого слова. Категорії допомагають орієнтуватися, але стають пасткою, коли їх плутають із готовим описом особистості."""


def channel(mode=ChannelMode.EDITORIAL):
    return ChannelConfig(
        id=2, name="ПРОДАНО!", telegram_chat_id="-1000",
        mode=mode, policy=ChannelPolicy(channel_id=2),
    )


def source(title=TITLE, raw=RAW, url="https://shots.net/news/view/question-time-were-getting-better-at-getting-it-wrong"):
    return {
        "id": 74792, "title": title, "raw_text": raw,
        "source_url": url, "canonical_source_url": url, "channel_id": 2,
        "source_id": 102, "source_name": "Shots"
    }


def test_screenshot_source_rejected_before_selector_and_writer():
    row = source()
    assert "EDITORIAL_MULTI_STORY_PAGE_CARDS" in multi_story_page_cards_reason(row)
    outcome = EditorialEngine._select_editorial(None, channel(), row)
    assert outcome.decision == Decision.REJECT
    assert outcome.fit_score == 0


def test_queued_ready_older_version_veto_before_telegram():
    row=source()
    assert "EDITORIAL_MULTI_STORY_PAGE_CARDS" in hard_editorial_reject(channel(), row, FINAL)
    assert any("EDITORIAL_MULTI_STORY_PAGE_CARDS" in issue for issue in prepublish_quality_issues(channel(),row,FINAL))


def test_actual_hero_single_story_with_sections_is_not_blocked():
    one = (
        "Brand built a new creative activation\n"
        "The initiative brought cinema artwork to a local exhibition and won a client contract.\n"
        "Visitors tried the installation at the opening. The exhibition took three weeks to assemble."
    )
    assert not multi_story_page_cards_reason(source(
        title="Brand built a new creative activation", raw=one))


def test_compilation_named_in_title_not_automatically_rejected():
    item=source(title="IKEA Skyrim Nike Mbappé fandom examples")
    assert not multi_story_page_cards_reason(item)


def test_other_publishers_with_normal_article_not_rejected():
    item=source(title="Nike and On battle for athlete endorsements",raw=
        "Nike's athlete branding has changed as sports brands compete over a single high-profile ambassador. "
        "The report includes views from marketing experts. The story follows one endorsement, "
        "its consequences and reasons the marketer made the move.",
        url="https://somepublisher.com/news/athlete-endorsement")
    assert multi_story_page_cards_reason(item)==""


def test_telegram_message_not_treated_as_web_card_grid():
    item=source(url="https://t.me/news/1234")
    assert multi_story_page_cards_reason(item)==""


def test_missing_source_title_or_short_or_plain_text_is_not_guessed():
    assert multi_story_page_cards_reason(source(title="Just news")) == ""
    assert multi_story_page_cards_reason(source(raw="This is a short source.")) == ""
