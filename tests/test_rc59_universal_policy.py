from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_rc59_business_logic_contains_no_specific_channel_names():
    source = Path("telegram_autopilot/rc59_universal_policy.py").read_text(encoding="utf-8")
    assert "CTRL+UA" not in source
    assert "ПРОДАНО" not in source
    assert "channel_kind(" not in source


def test_default_policy_is_generic_and_valid_for_new_channel():
    from telegram_autopilot.rc59_universal_policy import default_policy

    policy = default_policy(None)
    assert policy.purpose
    assert policy.selection_rules
    assert policy.media_policy == "required"
    assert policy.target_min_chars < policy.target_max_chars
    assert "member 'selection_rules'" not in policy.selection_rules


def test_policy_prompt_does_not_depend_on_channel_name(monkeypatch):
    from telegram_autopilot import rc52_feedback
    from telegram_autopilot.rc59_universal_policy import ChannelPolicy, _writer_prompt

    monkeypatch.setattr(rc52_feedback, "style_memory_block", lambda *a, **k: "")
    policy = ChannelPolicy(
        purpose="Міські новини та транспорт",
        audience="Мешканці міста",
        selection_rules="Брати зміни транспорту та міської інфраструктури",
        rejection_rules="Не брати спорт і шоу-бізнес",
    )
    article = {
        "title": "City opens a new tram line",
        "raw_text": ("The city opened a new tram line connecting two districts. " * 40),
    }
    selector = {"angle": "Нова транспортна лінія", "topic_tags": ["транспорт"], "fit_score": 90}
    a = _writer_prompt(policy, SimpleNamespace(id=1, name="Alpha"), article, selector, hard_limit=900)
    b = _writer_prompt(policy, SimpleNamespace(id=1, name="Totally Different Name"), article, selector, hard_limit=900)
    assert a == b


def test_refusal_meta_guard_blocks_exact_class_of_live_failure():
    from telegram_autopilot.rc59_universal_policy import refusal_meta_reason

    text = (
        "Вибачте, я не можу підготувати пост, оскільки у наданому джерелі немає "
        "жодної маркетингової механіки чи брендової активації, а тема не відповідає фокусу каналу."
    )
    assert refusal_meta_reason(text)
    assert refusal_meta_reason("Компанія відкрила новий центр у Києві. Проєкт запрацює восени.") == ""


def test_fire_is_style_only_and_does_not_change_topic_score():
    from telegram_autopilot.rc59_universal_policy import score_against_feedback_rc59

    article = {"title": "Robot prototype uses a new sensor", "raw_text": "Engineers built a robot prototype with a sensor."}
    row = {
        "article_id": 1,
        "title": "Robot prototype uses a new sensor",
        "raw_text": "Engineers built a robot prototype with a sensor.",
        "published_at": "2099-01-01T00:00:00+00:00",
        "likes": 0,
        "dislikes": 0,
        "fires": 5,
        "views": 0,
        "audience_total": 0,
    }
    score = score_against_feedback_rc59(article, [row])
    assert score.score == 0
    assert score.positive == 0
    assert score.negative == 0
    assert score.hard_suppress is False


def test_dislike_can_suppress_only_close_topic_without_channel_type():
    from telegram_autopilot.rc59_universal_policy import score_against_feedback_rc59

    article = {"title": "New battery prototype for electric buses", "raw_text": "Engineers tested a new battery prototype for electric buses."}
    row = {
        "article_id": 42,
        "title": "New battery prototype for electric buses",
        "raw_text": "Engineers tested a new battery prototype for electric buses.",
        "published_at": "2099-01-01T00:00:00+00:00",
        "likes": 0,
        "dislikes": 1,
        "fires": 1,
        "views": 0,
    }
    score = score_against_feedback_rc59(article, [row])
    assert score.score < 0
    assert score.hard_suppress is True
    assert score.matched_article_id == 42


def test_selector_parser_is_strict_and_conservative():
    from telegram_autopilot.rc59_universal_policy import _parse_selector

    published = _parse_selector('{"decision":"publish","fit_score":88,"reason":"fit","angle":"focus","topic_tags":["a","b"]}')
    assert published["decision"] == "publish"
    assert published["fit_score"] == 88

    low = _parse_selector('{"decision":"publish","fit_score":20,"reason":"weak","angle":"focus","topic_tags":[]}')
    assert low["decision"] == "reject"
    assert low["angle"] == ""


def test_channel_policy_database_roundtrip(tmp_path):
    import telegram_autopilot.rc59_universal_policy as rc59
    from telegram_autopilot.database import Database

    rc59._install_database_patch()
    db = Database(tmp_path / "rc59.sqlite")
    channel_id = db.save_channel(
        channel_id=None,
        name="Any future channel",
        telegram_chat_id="@future",
        editorial_profile="Legacy custom editorial description",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
    )
    migrated = db.rc59_get_channel_policy(channel_id)
    assert "Legacy custom editorial description" in migrated.purpose

    custom = rc59.ChannelPolicy(
        channel_id=channel_id,
        purpose="Local culture",
        audience="City residents",
        selection_rules="Only new local cultural events",
        rejection_rules="Reject national politics",
        writing_rules="Two short paragraphs",
        style_rules="Friendly and clear",
        media_policy="optional",
        target_min_chars=220,
        target_max_chars=520,
    )
    db.rc59_save_channel_policy(custom)
    loaded = db.rc59_get_channel_policy(channel_id)
    assert loaded.purpose == "Local culture"
    assert loaded.selection_rules == "Only new local cultural events"
    assert loaded.media_policy == "optional"
    assert loaded.target_min_chars == 220
    assert loaded.target_max_chars == 520
