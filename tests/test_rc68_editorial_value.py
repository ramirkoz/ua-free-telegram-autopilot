from __future__ import annotations

from types import SimpleNamespace

import telegram_autopilot.rc68_editorial_value as rc68
from telegram_autopilot.ai_router import Result
from telegram_autopilot.rc59_universal_policy import ChannelPolicy


def test_s301_style_curiosity_only_story_is_rejected():
    data = {
        "novelty": 72,
        "consequence_or_insight": 34,
        "mechanism": 44,
        "reader_payoff": 43,
        "retellability": 53,
        "concrete_stakes": 18,
        "why_now": 24,
        "curiosity_only": True,
    }
    allowed, code, score = rc68.editorial_value_allowed(data)
    assert allowed is False
    assert code == "curiosity_only_without_payoff"
    assert score < 60


def test_coal_ash_style_resource_mechanism_story_passes():
    data = {
        "novelty": 88,
        "consequence_or_insight": 91,
        "mechanism": 86,
        "reader_payoff": 92,
        "retellability": 91,
        "concrete_stakes": 94,
        "why_now": 79,
        "curiosity_only": False,
    }
    allowed, code, score = rc68.editorial_value_allowed(data)
    assert allowed is True
    assert code == "pass"
    assert score >= 80


def test_editorial_mode_always_runs_universal_value_gate(monkeypatch):
    fit_result = Result("fit", "codex", "fit-model", "fit")
    value_result = Result("value", "gemini", "value-model", "value")
    events = []

    monkeypatch.setattr(rc68, "_monitoring", lambda _value: False)
    monkeypatch.setattr(
        rc68,
        "_run_channel_fit",
        lambda _policy, _article, *, channel_id: (
            events.append("fit") or fit_result,
            {"decision": "publish", "fit_score": 93, "reason": "on scope", "angle": "angle", "topic_tags": ["science"]},
        ),
    )
    monkeypatch.setattr(
        rc68,
        "_run_value_gate",
        lambda _article: (
            events.append("value") or {
                "novelty": 50,
                "consequence_or_insight": 20,
                "mechanism": 30,
                "reader_payoff": 35,
                "retellability": 40,
                "concrete_stakes": 10,
                "why_now": 20,
                "curiosity_only": True,
                "reason": "лише цікава картинка",
            },
            False,
            "curiosity_only_without_payoff",
            31,
            value_result,
        ),
    )

    result, data = rc68._run_selector(ChannelPolicy(), {"id": 7, "title": "story"}, channel_id=1)
    assert events == ["fit", "value"]
    assert result is value_result
    assert data["decision"] == "reject"
    assert "EDITORIAL_VALUE_REJECT" in data["reason"]


def test_monitoring_mode_bypasses_editorial_value_gate(monkeypatch):
    events = []
    monitoring_result = Result("monitor", "local-rule", "monitor", "monitor")

    monkeypatch.setattr(rc68, "_monitoring", lambda _value: True)
    monkeypatch.setattr(
        rc68,
        "_monitoring_selector",
        lambda _policy, _article, *, channel_id: (
            events.append("monitoring") or monitoring_result,
            {"decision": "publish", "fit_score": 100, "reason": "bypass", "angle": "", "topic_tags": []},
        ),
    )
    monkeypatch.setattr(rc68, "_run_channel_fit", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("channel fit must be bypassed")))
    monkeypatch.setattr(rc68, "_run_value_gate", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("value gate must be bypassed")))

    result, data = rc68._run_selector(ChannelPolicy(), {"id": 8}, channel_id=2)
    assert events == ["monitoring"]
    assert result is monitoring_result
    assert data["decision"] == "publish"


def test_monitoring_without_custom_exclusions_uses_no_ai():
    policy = ChannelPolicy()
    result, data = rc68._monitoring_selector(policy, {"id": 1, "title": "plain monitoring item"}, channel_id=3)
    assert result.provider == "local-rule"
    assert data["decision"] == "publish"
    assert "MONITORING_BYPASS" in data["reason"]


def test_monitoring_disables_topic_balance_and_related_spacing(monkeypatch):
    monkeypatch.setitem(rc68._PREV, "editorial_hold", lambda *_a, **_k: "topic_daily_cap:Medicine:2/2")
    monitoring = SimpleNamespace(channel_mode="monitoring")
    editorial = SimpleNamespace(channel_mode="editorial")
    assert rc68._editorial_hold_reason(monitoring, object(), []) == ""
    assert rc68._editorial_hold_reason(editorial, object(), []) == "topic_daily_cap:Medicine:2/2"


def test_monitoring_neutralizes_reaction_topic_suppression(monkeypatch):
    monkeypatch.setattr(rc68, "_monitoring", lambda _value: True)
    monkeypatch.setitem(rc68._PREV, "feedback_score", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("feedback scorer must be bypassed")))
    score = rc68._feedback_score({"channel_id": 9}, [])
    assert score.score == 0
    assert score.hard_suppress is False
    assert score.rated_posts == 0


def test_editorial_pending_ordering_is_preserved(monkeypatch):
    expected = [{"id": 11}, {"id": 10}]
    monkeypatch.setattr(rc68, "_monitoring", lambda _value: False)
    monkeypatch.setitem(rc68._PREV, "pending", lambda _db, _cid, _limit: expected)
    db = SimpleNamespace(get_channel=lambda _cid: SimpleNamespace(channel_mode="editorial"))
    assert rc68._pending_by_mode(db, 1, 20) == expected
