from __future__ import annotations

import json
from types import SimpleNamespace

from telegram_autopilot.database import Database
from telegram_autopilot.rc42_policy import (
    _generic_newsworthiness,
    balance_reject_reason,
    install_rc42_policy,
    lexical_category,
    parse_editorial_weights,
    serialize_editorial_weights,
)


def channel(name: str, weights) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        name=name,
        editorial_profile=f"Profile for {name}",
        editorial_weights_json=serialize_editorial_weights(weights),
    )


def row(title: str, category: str = "", raw: str = "") -> dict[str, str]:
    return {
        "id": "1",
        "title": title,
        "raw_text": raw or title,
        "editorial_category": category,
        "teaser_text": "",
        "event_summary": "",
        "full_article_uk": "",
    }


def test_rc42_empty_channel_has_no_global_topic_balance():
    ch = channel("Marketing", [])
    reason, category = balance_reject_reason(
        ch,
        row("Critical cyber vulnerability"),
        [row("Old cyber", "Cyber") for _ in range(10)],
        category="Cyber",
    )
    assert reason == ""
    assert category == ""


def test_rc42_channel_weights_are_independent():
    tech = channel("CTRL+UA", [{"name": "Cyber", "weight": 10}, {"name": "AI", "weight": 90}])
    marketing = channel("Marketing", [{"name": "SEO", "weight": 60}, {"name": "Social media", "weight": 40}])
    recent_tech = [row(f"Security {i}", "Cyber") for i in range(6)] + [row(f"AI {i}", "AI") for i in range(4)]
    reason, category = balance_reject_reason(tech, row("Another CVE"), recent_tech, category="Cyber")
    assert reason.startswith("EDITORIAL_WEIGHT_RC42_SKIP")
    assert category == "Cyber"

    reason, category = balance_reject_reason(marketing, row("Instagram changes ad attribution"), recent_tech, category="")
    assert reason == ""
    assert category == ""


def test_rc42_zero_weight_means_operator_disabled_category():
    ch = channel("Marketing", [{"name": "Crypto", "weight": 0}, {"name": "SEO", "weight": 100}])
    reason, category = balance_reject_reason(ch, row("Crypto campaign"), [], category="Crypto")
    assert reason.startswith("EDITORIAL_WEIGHT_RC42_SKIP")
    assert category == "Crypto"


def test_rc42_weights_do_not_need_to_sum_to_100():
    ch = channel("Marketing", [{"name": "SEO", "weight": 3}, {"name": "Social media", "weight": 2}, {"name": "Email", "weight": 1}])
    parsed = parse_editorial_weights(ch)
    assert [item["weight"] for item in parsed] == [3.0, 2.0, 1.0]


def test_rc42_lexical_classifier_uses_operator_names():
    categories = [{"name": "SEO", "weight": 50}, {"name": "Social media", "weight": 50}]
    assert lexical_category(row("New SEO analytics tool for publishers"), categories) == "SEO"
    assert lexical_category(row("Social media platforms change creator metrics"), categories) == "Social media"


def test_rc42_generic_gate_does_not_reject_marketing_news_by_domain():
    article = row(
        "Brand launches new subscription pricing campaign",
        raw="The company launched a campaign with new pricing and retail positioning.",
    )
    assert _generic_newsworthiness(article) == ""


def test_rc42_generic_gate_still_rejects_buying_guide_junk():
    assert _generic_newsworthiness(row("Best accessories buying guide for your laptop"))


def test_rc42_additive_schema_preserves_existing_database(tmp_path):
    install_rc42_policy()
    db = Database(tmp_path / "rc42.sqlite3")
    channel_id = db.save_channel(
        channel_id=None,
        name="Marketing",
        telegram_chat_id="@marketing",
        editorial_profile="Marketing, advertising, analytics and content.",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
    )
    db.set_channel_editorial_weights(
        channel_id,
        [{"name": "SEO", "weight": 40}, {"name": "Social media", "weight": 60}],
    )
    saved = db.get_channel(channel_id)
    assert saved is not None
    payload = json.loads(saved.editorial_weights_json)
    assert payload == [{"name": "SEO", "weight": 40.0}, {"name": "Social media", "weight": 60.0}]
    with db.connect() as con:
        channel_columns = {row[1] for row in con.execute("PRAGMA table_info(channels)")}
        article_columns = {row[1] for row in con.execute("PRAGMA table_info(articles)")}
    assert "editorial_weights_json" in channel_columns
    assert "editorial_category" in article_columns
