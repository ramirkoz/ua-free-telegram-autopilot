from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from telegram_autopilot.ai_router import AIRouterError
from telegram_autopilot.models import Channel
from telegram_autopilot.rc49_policy import (
    _build_ua_human_writer_prompt,
    _human_readability_issues,
    balance_reject_reason_rc49,
    ctrl_ua_niche_reject_reason,
    is_ctrl_ua,
)


def channel(name: str = "CTRL+UA", weights=None) -> Channel:
    return Channel(
        id=1,
        name=name,
        telegram_chat_id="@test",
        editorial_profile="Technology, science, AI and security for a broad audience.",
        enabled=True,
        include_source_link=True,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
        created_at="",
        updated_at="",
        editorial_weights_json=json.dumps(weights or [
            {"name": "Cybersecurity & Privacy", "weight": 5},
            {"name": "AI & Agents", "weight": 20},
        ]),
    )


def article(title: str, raw: str = ""):
    return {"id": 77, "title": title, "raw_text": raw, "editorial_category": ""}


def test_ctrl_ua_name_detection():
    assert is_ctrl_ua(channel("CTRL+UA"))
    assert is_ctrl_ua(channel("Ctrl UA"))
    assert not is_ctrl_ua(channel("ПРОДАНО!"))


def test_rejects_confirmed_narrow_amiga_story():
    reason = ctrl_ua_niche_reject_reason(
        article("Amiga gets a new life on ARM", "AROS now supports Raspberry Pi and THEA1200 uses Amiberry with AmigaOS.")
    )
    assert "EDITORIAL_BREADTH_RC49_SKIP" in reason


def test_rejects_confirmed_boot_to_basic_story():
    reason = ctrl_ua_niche_reject_reason(
        article("All the best computers boot to BASIC", "Tarjan created Thoreau BASIC, a boot-to-BASIC UEFI environment compatible with GW-BASIC.")
    )
    assert "EDITORIAL_BREADTH_RC49_SKIP" in reason


def test_does_not_ban_raspberry_pi_generically():
    assert not ctrl_ua_niche_reject_reason(
        article("Critical Raspberry Pi supply-chain vulnerability fixed", "A security update fixes a remotely exploitable flaw.")
    )


def test_positive_weights_are_soft_not_quota_rejects():
    ch = channel()
    recent = [
        {"editorial_category": "Cybersecurity & Privacy", "published_at": "2026-08-28T00:00:00+00:00"}
        for _ in range(12)
    ]
    reason, category = balance_reject_reason_rc49(
        ch,
        article("Major browser zero-day exploited", "A browser vulnerability is actively exploited."),
        recent,
        category="Cybersecurity & Privacy",
    )
    assert reason == ""
    assert category == "Cybersecurity & Privacy"


def test_zero_weight_is_still_explicit_block():
    ch = channel(weights=[{"name": "Retro", "weight": 0}, {"name": "AI", "weight": 100}])
    reason, category = balance_reject_reason_rc49(
        ch, article("Something"), [], category="Retro"
    )
    assert "вагу 0" in reason
    assert category == "Retro"


def test_unclassified_is_fail_closed():
    ch = channel()
    with pytest.raises(AIRouterError):
        balance_reject_reason_rc49(ch, article("Something"), [], category="__UNCLASSIFIED__")


def test_readability_gate_catches_extreme_sentence_train():
    long_sentence = " ".join(["слово"] * 55) + "."
    assert _human_readability_issues(long_sentence)


def test_readability_gate_allows_normal_news_rhythm():
    text = (
        "Anthropic додала браузер у Claude. Він може сам відкривати сторінки й заповнювати форми. "
        "Основний браузер користувача при цьому лишається окремим."
    )
    assert _human_readability_issues(text) == ()


def test_ua_writer_prompt_is_read_aloud_first_not_checklist_polish(monkeypatch):
    import telegram_autopilot.rc48_learning as rc48

    monkeypatch.setattr(rc48, "_format_memory_block", lambda *args, **kwargs: "")
    prompt = _build_ua_human_writer_prompt(
        channel(),
        article("Claude gets a browser", "Claude can open websites and fill forms."),
        "Главное — Claude получил встроенный браузер.",
        hard_limit=900,
    )
    assert "Напиши фінальний пост З НУЛЯ" in prompt
    assert "легко читатися людиною вголос" in prompt
    assert "не перетворюй новину на каталог характеристик" in prompt
    assert "Не перекладай" in prompt
