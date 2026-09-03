from __future__ import annotations

from types import SimpleNamespace

import telegram_autopilot.rc65_universal_final_editor as rc65
from telegram_autopilot.models import Decision


def _decision(text: str = "Безпечний український текст.") -> Decision:
    return Decision(
        decision="publish", duplicate_of=None, reason="safe", event_key="test",
        event_summary=text, headline_uk="", telegram_teaser=text, full_article_uk=text,
        media_captions_uk={}, confidence=0.9, provider="codex", model="test",
    )


def test_behavior_route_accepts_strong_commercial_mechanic_without_campaign_creative():
    route = rc65._marketing_route({
        "fit_score": 42,
        "human_interest_score": 52,
        "friend_share_score": 38,
        "creative_surprise_score": 28,
        "marketing_mechanic_score": 72,
        "non_marketer_hook": "платформа змушує користувачів міняти спосіб оплати",
    })

    assert route == "behavior"


def test_boring_sponsorship_does_not_pass_behavior_route():
    route = rc65._marketing_route({
        "fit_score": 65,
        "human_interest_score": 45,
        "friend_share_score": 25,
        "creative_surprise_score": 20,
        "marketing_mechanic_score": 66,
        "non_marketer_hook": "бренд став партнером ліги",
    })

    assert route == ""


def test_selector_pass_is_cached_so_retry_resumes_after_selector(monkeypatch):
    rc65._SELECTOR_CACHE.clear()
    calls = {"count": 0}
    result = SimpleNamespace(
        text='{"decision":"publish","fit_score":42,"reason":"mechanic","angle":"payments","topic_tags":["payments"],'
             '"human_interest_score":52,"creative_surprise_score":28,"marketing_mechanic_score":72,'
             '"friend_share_score":38,"non_marketer_hook":"людей змушують міняти спосіб оплати"}'
    )
    rejected = {
        "decision": "reject", "fit_score": 42, "reason": "RC62 HUMAN_INTEREST_REJECT: test",
        "angle": "", "topic_tags": ["payments"], "human_interest_score": 52,
        "creative_surprise_score": 28, "marketing_mechanic_score": 72,
        "friend_share_score": 38, "non_marketer_hook": "людей змушують міняти спосіб оплати",
    }

    def previous(policy, article, channel_id=0):
        calls["count"] += 1
        return result, rejected

    monkeypatch.setattr(rc65, "_PREV_SELECTOR", previous)
    monkeypatch.setattr("telegram_autopilot.rc62_editorial_control._marketing", lambda policy: True)
    article = {"id": 7032, "title": "X Money changes payment behavior"}

    _r1, parsed1 = rc65._run_selector_rc65(SimpleNamespace(), article, channel_id=2)
    _r2, parsed2 = rc65._run_selector_rc65(SimpleNamespace(), article, channel_id=2)

    assert parsed1["decision"] == "publish"
    assert parsed1["reason"].startswith("RC65 MARKETING_ROUTE_PASS route=behavior")
    assert parsed2["decision"] == "publish"
    assert calls["count"] == 1


def test_decide_applies_final_editor_to_every_published_channel(monkeypatch):
    seen = []

    def previous(channel, article, recent, *, hard_limit, format_marker=None):
        return _decision()

    def final_edit(channel, article, decision, *, hard_limit):
        seen.append((channel.id, article["id"]))
        return decision

    monkeypatch.setattr(rc65, "_PREV_DECIDE", previous)
    monkeypatch.setattr(rc65, "_universal_final_edit", final_edit)

    rc65._decide_rc65(SimpleNamespace(id=1, name="CTRL+UA"), {"id": 10, "title": "A"}, [], hard_limit=900)
    rc65._decide_rc65(SimpleNamespace(id=2, name="ПРОДАНО!"), {"id": 11, "title": "B"}, [], hard_limit=900)

    assert seen == [(1, 10), (2, 11)]


def test_decide_does_not_run_final_editor_for_reject(monkeypatch):
    called = {"editor": 0}

    def previous(channel, article, recent, *, hard_limit, format_marker=None):
        d = _decision()
        return Decision(
            decision="reject", duplicate_of=None, reason="no", event_key="reject",
            event_summary="", headline_uk="", telegram_teaser="", full_article_uk="",
            media_captions_uk={}, confidence=0.9, provider="local-rule", model="test",
        )

    def final_edit(channel, article, decision, *, hard_limit):
        called["editor"] += 1
        return decision

    monkeypatch.setattr(rc65, "_PREV_DECIDE", previous)
    monkeypatch.setattr(rc65, "_universal_final_edit", final_edit)

    result = rc65._decide_rc65(SimpleNamespace(id=3), {"id": 12, "title": "C"}, [], hard_limit=900)

    assert result.decision == "reject"
    assert called["editor"] == 0
