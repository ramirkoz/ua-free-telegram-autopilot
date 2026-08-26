from telegram_autopilot.rc41_policy import (
    newsworthiness_reject_reason_rc41,
    primary_topic_rc41,
    topic_balance_reject_reason_rc41,
)


def row(title: str, raw: str = "") -> dict[str, str]:
    return {
        "title": title,
        "raw_text": raw or title,
        "teaser_text": "",
        "event_summary": "",
        "full_article_uk": "",
    }


def mixed_recent() -> list[dict[str, str]]:
    return [
        row("Critical Gitea vulnerability exploited in attacks"),
        row("New Windows security flaw patched"),
        row("Claude adds browser agents"),
        row("Humanoid robot learns a task from one demonstration"),
        row("Researchers publish a new battery study"),
        row("Xbox gets a new accessibility controller"),
        row("Open-source video toolkit lands on GitHub"),
        row("NASA telescope maps a distant galaxy"),
        row("Startup raises funding for AI glasses"),
        row("New GPU architecture improves inference"),
    ]


def test_rc41_classifies_practical_open_source_separately_from_ai():
    article = row(
        "Open-source toolkit for AI agents lands on GitHub",
        "The repository includes a plugin framework and CLI for developers.",
    )
    assert primary_topic_rc41(article) == "tools_open_source"


def test_rc41_blocks_third_cyber_slot_in_last_ten():
    article = row(
        "Another critical CVE found in enterprise software",
        "Researchers disclosed CVE-2026-99999, a critical vulnerability in a server product.",
    )
    reason = topic_balance_reject_reason_rc41(article, mixed_recent())
    assert reason.startswith("TOPIC_BALANCE_RC41_SKIP")
    assert "кібербезпека" in reason


def test_rc41_plain_cve_is_not_a_balance_bypass_anymore():
    article = row(
        "CVE-2026-60004 rated critical",
        "The critical vulnerability can allow code execution after repository write access.",
    )
    assert topic_balance_reject_reason_rc41(article, mixed_recent())


def test_rc41_true_broad_emergency_can_bypass_mix():
    article = row(
        "Actively exploited zero-day used in widespread attacks",
        "The zero-day is used in widespread attacks against millions of devices.",
    )
    assert topic_balance_reject_reason_rc41(article, mixed_recent()) == ""


def test_rc41_rescues_genuinely_useful_nonshopping_resource():
    article = row(
        "How to use an open-source toolkit for local AI",
        "A new GitHub repository provides a free toolkit, CLI and plugin framework for local models.",
    )
    assert newsworthiness_reject_reason_rc41(article) == ""


def test_rc41_does_not_rescue_shopping_guides():
    article = row(
        "Best accessories buying guide for your laptop",
        "Our picks include discounted docks and chargers. Shop now with a coupon.",
    )
    assert newsworthiness_reject_reason_rc41(article)


def test_rc41_ai_still_has_more_editorial_room_than_cyber():
    recent = [
        row("Claude launches new agent tools"),
        row("Gemini adds multimodal agent mode"),
        row("Robot learns warehouse task"),
        row("New battery research published"),
        row("Windows adds privacy controls"),
        row("GitHub releases an open-source library"),
        row("NASA releases telescope images"),
        row("New processor targets laptops"),
        row("Tech startup raises a new round"),
        row("New display technology reaches laptops"),
    ]
    article = row("Qwen releases a new multimodal AI model")
    assert topic_balance_reject_reason_rc41(article, recent) == ""
