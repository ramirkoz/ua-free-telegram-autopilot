from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import telegram_autopilot.rc66_editorial_queue as rc66
import telegram_autopilot.rc66_tags as tagsmod


def channel(**overrides):
    base = dict(name="CTRL+UA", editorial_profile="science technology news", publish_24h=False, publish_start="07:00", publish_end="00:00", publish_immediately=False, min_publish_interval_minutes=10, topic_balance_enabled=True, topic_daily_limit=2, related_spacing_posts=5)
    base.update(overrides)
    return SimpleNamespace(**base)


def row(*, major="Other", minor="", title="", text="", published_at=""):
    tags = tagsmod.StoryTags(major, minor, (), (), ())
    return {"tags_json": tags.as_json(), "title": title, "raw_text": text, "teaser_text": text, "event_summary": text, "published_at": published_at}


def test_publication_window_supports_daytime_and_overnight():
    tz = timezone(timedelta(hours=3))
    c = channel(publish_start="07:00", publish_end="23:00")
    assert rc66.publication_window_open(c, now=datetime(2026, 9, 4, 12, 0, tzinfo=tz))
    assert not rc66.publication_window_open(c, now=datetime(2026, 9, 4, 2, 0, tzinfo=tz))
    c2 = channel(publish_start="22:00", publish_end="06:00")
    assert rc66.publication_window_open(c2, now=datetime(2026, 9, 4, 23, 30, tzinfo=tz))
    assert rc66.publication_window_open(c2, now=datetime(2026, 9, 5, 4, 30, tzinfo=tz))
    assert not rc66.publication_window_open(c2, now=datetime(2026, 9, 4, 12, 0, tzinfo=tz))
    assert rc66.publication_window_open(channel(publish_24h=True), now=datetime(2026, 9, 4, 2, 0, tzinfo=tz))


def test_daily_major_topic_cap_holds_third_medicine_story():
    tz = timezone(timedelta(hours=3)); now = datetime(2026, 9, 4, 18, 0, tzinfo=tz)
    recent = [
        row(major="Medicine & Health", minor="Neurology", published_at=(now - timedelta(hours=1)).isoformat()),
        row(major="Medicine & Health", minor="Gene editing", published_at=(now - timedelta(hours=3)).isoformat()),
    ]
    candidate = tagsmod.StoryTags("Medicine & Health", "Xenotransplantation", (), (), ())
    assert rc66.editorial_hold_reason(channel(topic_daily_limit=2), candidate, recent, now=now).startswith("topic_daily_cap:Medicine & Health:2/2")


def test_related_but_different_patient_story_requires_five_other_posts():
    tz = timezone(timedelta(hours=3)); now = datetime(2026, 9, 4, 18, 0, tzinfo=tz)
    candidate = tagsmod.StoryTags("Medicine & Health", "Xenotransplantation", ("Patient B",), (), ())
    recent = [
        row(major="AI & Software", minor="AI models & agents", published_at=(now - timedelta(minutes=10)).isoformat()),
        row(major="Space & Astronomy", minor="Planetary science", published_at=(now - timedelta(minutes=20)).isoformat()),
        row(major="Animals & Nature", minor="Wild animal behavior", published_at=(now - timedelta(minutes=30)).isoformat()),
        row(major="Consumer Tech & Hardware", minor="PC hardware", published_at=(now - timedelta(minutes=40)).isoformat()),
        row(major="Medicine & Health", minor="Xenotransplantation", published_at=(now - timedelta(minutes=50)).isoformat()),
    ]
    assert rc66.editorial_hold_reason(channel(topic_daily_limit=10, related_spacing_posts=5), candidate, recent, now=now).startswith("related_spacing:Xenotransplantation")
    recent.insert(0, row(major="Science & Engineering", minor="Materials & energy", published_at=(now - timedelta(minutes=5)).isoformat()))
    assert rc66.editorial_hold_reason(channel(topic_daily_limit=10, related_spacing_posts=5), candidate, recent, now=now) == ""


def test_daily_cap_resets_next_day_but_spacing_does_not_depend_on_midnight():
    tz = timezone(timedelta(hours=3)); now = datetime(2026, 9, 5, 0, 20, tzinfo=tz); yesterday = now - timedelta(hours=2)
    candidate = tagsmod.StoryTags("Medicine & Health", "Metabolism & obesity", (), (), ())
    recent = [row(major="Medicine & Health", minor="Neurology", published_at=yesterday.isoformat()), row(major="Medicine & Health", minor="Gene editing", published_at=(yesterday - timedelta(hours=1)).isoformat())]
    assert rc66.editorial_hold_reason(channel(topic_daily_limit=2, related_spacing_posts=0), candidate, recent, now=now) == ""
    kidney = tagsmod.StoryTags("Medicine & Health", "Xenotransplantation", (), (), ())
    recent2 = [row(major="Medicine & Health", minor="Xenotransplantation", published_at=yesterday.isoformat())]
    assert rc66.editorial_hold_reason(channel(topic_daily_limit=10, related_spacing_posts=5), kidney, recent2, now=now).startswith("related_spacing:")


def test_structural_gate_blocks_abrupt_thought():
    assert rc66.structural_issue("Дослідники побачили ефект, але")
    assert rc66.structural_issue("Головна причина полягає в тому, що")
    assert rc66.structural_issue("Цей результат означає:")
    assert rc66.structural_issue("Це завершена думка. Інша фраза без фінальної крапки")
    assert rc66.structural_issue("Це завершена й нормальна думка.") == ""


def test_tags_separate_kidney_event_topic_from_other_medicine():
    a = tagsmod.extract_story_tags("Pig kidney kept a patient off dialysis for 271 days", "genetically edited pig kidney transplant")
    b = tagsmod.extract_story_tags("Another patient sets pig kidney transplant record", "porcine kidney 285 days")
    c = tagsmod.extract_story_tags("CRISPR therapy cuts LDL cholesterol", "gene editing treatment for cholesterol")
    assert a.major == b.major == "Medicine & Health"
    assert a.minor == b.minor == "Xenotransplantation"
    assert c.minor != "Xenotransplantation"
    assert tagsmod.strong_overlap(a, b)


def test_multisource_footer_contains_every_source():
    urls = ["https://one.example/a", "https://two.example/b", "https://three.example/c"]
    caption, clickable = rc66._caption("Короткий завершений матеріал.", urls, hard_limit=900)
    assert clickable == ""
    assert "Джерела:" in caption
    assert all(url in caption for url in urls)


def test_selector_admits_relevant_borderline_story_to_pool(monkeypatch):
    class Result: text = "{}"
    def previous(_policy, _article, *, channel_id=0):
        return Result(), {"decision": "reject", "fit_score": 72, "reason": "good but below old threshold", "topic_tags": ["science"]}
    monkeypatch.setitem(rc66._PREV, "selector", previous)
    policy = SimpleNamespace(purpose="science news", audience="", selection_rules="", rejection_rules="", positive_examples="", negative_examples="", extra_instructions="", selector_extra_prompt="")
    _result, parsed = rc66._selector(policy, {"id": 1, "title": "Useful research"}, channel_id=1)
    assert parsed["decision"] == "publish"
    assert "POOL_ADMISSION" in parsed["reason"]
