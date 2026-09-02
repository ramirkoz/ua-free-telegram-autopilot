from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_autopilot.database import Database
from telegram_autopilot.models import CollectedArticle
from telegram_autopilot.rc33_policy import install_rc33_policy
from telegram_autopilot.rc53_hardening import install_rc53_hardening
from telegram_autopilot.rc61_runtime_fix import install_rc61_runtime_fix
from telegram_autopilot.rc62_editorial_control import (
    _enforce_marketing_interest,
    _parse_marketing,
    _same_product_cycle,
    obvious_language_corruption,
    pending,
    source_link_entities,
)


def test_marketing_interest_gate_rejects_trade_pretty_but_weak_story():
    parsed = {
        "decision": "publish", "fit_score": 88, "reason": "brand campaign", "angle": "nice visual",
        "topic_tags": ["campaign"], "human_interest_score": 59, "creative_surprise_score": 77,
        "marketing_mechanic_score": 71, "friend_share_score": 55, "non_marketer_hook": "",
    }
    result = _enforce_marketing_interest(parsed)
    assert result["decision"] == "reject"
    assert "HUMAN_INTEREST_REJECT" in result["reason"]


def test_marketing_interest_gate_keeps_volvo_like_intrinsic_story():
    parsed = {
        "decision": "publish", "fit_score": 92, "reason": "paradox", "angle": "brand advertises competitors",
        "topic_tags": ["campaign"], "human_interest_score": 91, "creative_surprise_score": 89,
        "marketing_mechanic_score": 80, "friend_share_score": 86, "non_marketer_hook": "open safety inventions",
    }
    result = _enforce_marketing_interest(parsed)
    assert result["decision"] == "publish"


def test_marketing_interest_gate_keeps_strong_behaviour_story_without_festival_creative():
    parsed = {
        "decision": "publish", "fit_score": 84, "reason": "shopping behaviour", "angle": "smart carts change spend",
        "topic_tags": ["behavior"], "human_interest_score": 88, "creative_surprise_score": 46,
        "marketing_mechanic_score": 76, "friend_share_score": 82, "non_marketer_hook": "people spent more",
    }
    result = _enforce_marketing_interest(parsed)
    assert result["decision"] == "publish"


def test_marketing_selector_requires_explicit_interest_scores():
    raw = json.dumps({
        "decision": "publish", "fit_score": 90, "reason": "x", "angle": "y", "topic_tags": ["a"],
        "human_interest_score": 80, "creative_surprise_score": 70,
        "marketing_mechanic_score": 65, "friend_share_score": 75,
        "non_marketer_hook": "interesting outside the trade",
    }, ensure_ascii=False)
    parsed = _parse_marketing(raw)
    assert parsed["human_interest_score"] == 80
    assert parsed["friend_share_score"] == 75


def test_same_product_cycle_catches_two_different_dlss5_articles():
    old = {
        "title": "Nvidia launches DLSS 5 in NBA 2K27",
        "teaser_text": "Nvidia запускає DLSS 5. Система змінює тіні, деталі, персонажів і кадри. Розробники отримають контроль інтенсивності.",
    }
    hit = _same_product_cycle(
        "Nvidia DLSS 5 explained",
        "DLSS 5 від Nvidia працює як AI-фільтр кадру: змінює тіні, деталі, персонажів і освітлення. Розробники керують інтенсивністю.",
        old,
    )
    assert hit is not None
    assert "dlss 5" in hit[1]


def test_source_link_entity_survives_video_footer():
    text = "Текст поста.\n\nДжерело\n\n🎬 Відео: https://youtu.be/test"
    raw = source_link_entities(text, "https://example.com/story")
    entities = json.loads(raw)
    assert len(entities) == 1
    assert entities[0]["type"] == "text_link"
    assert entities[0]["url"] == "https://example.com/story"


def test_observed_live_language_corruptions_are_blocked():
    assert obvious_language_corruption("всі автомобілі запік селені")
    assert obvious_language_corruption("яскравий зірковий сліду вальник")
    assert obvious_language_corruption("частинки падають у вузькому смузі")
    assert obvious_language_corruption("якщо мод дери викрутять")
    assert obvious_language_corruption("потрібна непісної пасти")
    assert not obvious_language_corruption("Volvo показала власні винаходи в автомобілях інших брендів.")


def test_pending_saturation_defers_third_same_source_without_rejecting(tmp_path: Path):
    install_rc33_policy()
    install_rc53_hardening()
    install_rc61_runtime_fix()
    db = Database(tmp_path / "rc62.sqlite3")
    cid = db.save_channel(
        channel_id=None, name="CTRL+UA", telegram_chat_id="@test", editorial_profile="science technology",
        enabled=True, include_source_link=False, poll_interval_minutes=5, min_publish_interval_minutes=0,
        dedupe_window_hours=72, max_age_hours=24, max_posts_per_cycle=3,
    )
    sid1 = db.save_source(source_id=None, channel_id=cid, kind="rss", name="BleepingComputer", url="https://a.example/feed", enabled=True, priority=95)
    sid2 = db.save_source(source_id=None, channel_id=cid, kind="rss", name="Science", url="https://b.example/feed", enabled=True, priority=90)
    sources = {s.id: s for s in db.list_sources(cid)}
    now = datetime.now(timezone.utc).astimezone()

    for idx in range(2):
        aid = db.insert_collected(sources[sid1], CollectedArticle(
            f"old{idx}", f"Security breach {idx}", f"https://a.example/{idx}", "cyber security breach malware exploit " * 40,
            now.isoformat(), ["image|https://a.example/x.jpg"]
        ), baseline=False)
        db.update_article(int(aid), status="published", published_at=(now - timedelta(hours=idx + 1)).isoformat(), teaser_text="cyber security breach malware exploit")

    blocked = db.insert_collected(sources[sid1], CollectedArticle(
        "newa", "Another security breach", "https://a.example/new", "cyber security breach exploit " * 40,
        now.isoformat(), ["image|https://a.example/y.jpg"]
    ), baseline=False)
    allowed = db.insert_collected(sources[sid2], CollectedArticle(
        "newb", "A space telescope discovery", "https://b.example/new", "space telescope astronomy research discovery " * 40,
        now.isoformat(), ["image|https://b.example/y.jpg"]
    ), baseline=False)

    import telegram_autopilot.rc62_editorial_control as rc62
    previous = rc62._PREV.get("pending")
    rc62._PREV["pending"] = Database.pending_articles
    try:
        rows = pending(db, cid, limit=5)
    finally:
        if previous is None: rc62._PREV.pop("pending", None)
        else: rc62._PREV["pending"] = previous
    ids = [int(r["id"]) for r in rows]
    assert int(allowed) in ids
    assert int(blocked) not in ids
    assert db.get_article(int(blocked))["status"] == "new"
