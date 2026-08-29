from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram_autopilot import rc51_feedback as rc51
from telegram_autopilot import rc52_feedback as rc52


def _stamp(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _row(*, likes=0, dislikes=0, fires=0, teaser="Published Telegram text", hours=2):
    return {
        "article_id": 1,
        "title": "AI chip launch for laptops",
        "raw_text": "A new AI chip launches for laptops with on-device inference.",
        "event_summary": "",
        "teaser_text": teaser,
        "likes": likes,
        "dislikes": dislikes,
        "fires": fires,
        "published_at": _stamp(hours),
        "checked_at": _stamp(hours),
    }


def test_topic_signal_ignores_fire_completely():
    assert rc52.topic_feedback_signal(_row(fires=2)) == 0
    assert rc52.topic_feedback_signal(_row(likes=1, fires=2)) == 1
    assert rc52.topic_feedback_signal(_row(dislikes=1, fires=2)) == -2


def test_style_signal_uses_only_fire():
    assert rc52.style_feedback_signal(_row(likes=2)) == 0
    assert rc52.style_feedback_signal(_row(dislikes=2)) == 0
    assert rc52.style_feedback_signal(_row(fires=1)) == 1
    assert rc52.style_feedback_signal(_row(likes=1, dislikes=1, fires=2)) == 2


def test_like_and_dislike_keep_rc51_topic_decay_and_suppression_after_install():
    rc52.install_rc52_feedback()
    candidate = {"id": 9, "title": "AI chip launch for laptops", "raw_text": "A new AI chip launches for laptops with on-device inference.", "event_summary": ""}
    liked = rc51.score_against_feedback(candidate, [_row(likes=1)])
    fired = rc51.score_against_feedback(candidate, [_row(fires=1)])
    disliked = rc51.score_against_feedback(candidate, [_row(dislikes=1)])
    assert liked.score > 0
    assert fired.score == 0
    assert fired.hard_suppress is False
    assert disliked.score < 0
    assert disliked.hard_suppress is True


def test_fire_only_style_memory_does_not_use_like_or_dislike_as_style_signal(monkeypatch):
    class DB:
        def rc51_feedback_rows(self, *_args, **_kwargs):
            return [
                _row(likes=1, teaser="Liked topic but ordinary wording"),
                _row(dislikes=1, teaser="Disliked topic but ordinary wording"),
                _row(fires=1, teaser="Short vivid Telegram copy worth imitating"),
                _row(dislikes=1, fires=1, teaser="Good writing on a topic we do not want"),
            ]

    monkeypatch.setattr(rc51, "_ACTIVE_DB", DB())
    block = rc52.style_memory_block(
        type("Channel", (), {"id": 1})(),
        {"title": "AI chip launch for laptops", "raw_text": "AI chip laptops", "event_summary": ""},
        purpose="writing",
    )
    assert "Short vivid Telegram copy worth imitating" in block
    assert "Good writing on a topic we do not want" in block
    assert "Liked topic but ordinary wording" not in block
    assert "Disliked topic but ordinary wording" not in block
    assert "🔥 означає: текст написаний добре" in block


def test_selection_prompt_receives_no_style_memory(monkeypatch):
    class DB:
        def rc51_feedback_rows(self, *_args, **_kwargs):
            return [_row(fires=1, teaser="Excellent style sample")]

    monkeypatch.setattr(rc51, "_ACTIVE_DB", DB())
    assert rc52.style_memory_block(
        type("Channel", (), {"id": 1})(),
        {"title": "Story", "raw_text": "Story text", "event_summary": ""},
        purpose="selection",
    ) == ""
