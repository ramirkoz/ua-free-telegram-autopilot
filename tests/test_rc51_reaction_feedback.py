from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot import rc51_feedback as rc51


def _stamp(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _article(title: str, raw: str = ""):
    return {"id": 999, "title": title, "raw_text": raw, "event_summary": ""}


def _feedback(*, title: str, raw: str = "", likes: int = 0, dislikes: int = 0, fires: int = 0, hours: float = 2, article_id: int = 1):
    return {
        "article_id": article_id,
        "title": title,
        "raw_text": raw,
        "event_summary": "",
        "teaser_text": title,
        "likes": likes,
        "dislikes": dislikes,
        "fires": fires,
        "published_at": _stamp(hours),
        "checked_at": _stamp(hours),
    }


def test_no_reaction_is_neutral():
    rows = [_feedback(title="AI chip launch for laptops", likes=0, dislikes=0, fires=0)]
    score = rc51.score_against_feedback(_article("AI chip launch for laptops"), rows)
    assert score.score == 0
    assert score.rated_posts == 0
    assert score.hard_suppress is False


def test_fire_is_stronger_than_like():
    candidate = _article("Uber teen campaign returns for back to school", "Mother New York launches a creator campaign")
    liked = [_feedback(title="Uber teen campaign for back to school", raw="Mother New York creator campaign", likes=1)]
    fired = [_feedback(title="Uber teen campaign for back to school", raw="Mother New York creator campaign", fires=1)]
    like_score = rc51.score_against_feedback(candidate, liked)
    fire_score = rc51.score_against_feedback(candidate, fired)
    assert like_score.score > 0
    assert fire_score.score > like_score.score


def test_fresh_dislike_suppresses_only_close_story():
    row = _feedback(
        title="Uber teen back to school manifestation campaign",
        raw="Uber Teen Mother New York free rides food campaign schools",
        dislikes=1,
        hours=4,
        article_id=77,
    )
    close = rc51.score_against_feedback(
        _article("Uber Teen returns with back to school campaign", "Mother New York free rides food schools manifestation"),
        [row],
    )
    far = rc51.score_against_feedback(
        _article("Scientists reconstruct Jurassic insect sounds", "fossil wings Mongolia paleontology"),
        [row],
    )
    assert close.score < 0
    assert close.hard_suppress is True
    assert close.matched_article_id == 77
    assert far.hard_suppress is False


def test_dislike_expires_after_seven_days():
    row = _feedback(
        title="Uber teen back to school manifestation campaign",
        raw="Uber Teen Mother New York free rides food campaign schools",
        dislikes=1,
        hours=8 * 24,
    )
    score = rc51.score_against_feedback(
        _article("Uber Teen returns with back to school campaign", "Mother New York free rides food schools manifestation"),
        [row],
    )
    assert score.score == 0
    assert score.hard_suppress is False


def test_reaction_breakdown_reads_only_three_training_reactions():
    def result(emoji: str, count: int):
        return SimpleNamespace(reaction=SimpleNamespace(emoticon=emoji), count=count)

    message = SimpleNamespace(
        views=100,
        forwards=3,
        replies=SimpleNamespace(replies=2),
        reactions=SimpleNamespace(results=[
            result("👍", 2),
            result("👎", 1),
            result("🔥\ufe0f", 3),
            result("❤️", 9),
        ]),
    )
    assert rc51.reaction_breakdown(message) == (100, 3, 2, 2, 1, 3, 9)


def test_similarity_requires_more_than_one_brand_anchor_for_strong_match():
    weak, shared = rc51.similarity_parts(
        "Google launches Android memory rules",
        "Google celebrates a new office opening in London",
    )
    strong, strong_shared = rc51.similarity_parts(
        "Google launches Android memory rules for low RAM phones",
        "Google Android apps face new RAM memory limits on phones",
    )
    assert shared <= 1
    assert strong_shared >= 4
    assert strong > weak


def test_telegram_native_prompt_explicitly_rejects_site_style():
    prompt = rc51.build_ua_feedback_writer_prompt(
        SimpleNamespace(id=1, name="CTRL+UA"),
        _article("Google changes Android app memory limits", "Google will enforce memory limits for Android apps."),
        "Главное изменение — новые ограничения памяти.",
        hard_limit=850,
    )
    assert "Telegram, а не коротку статтю для сайту" in prompt
    assert "Для ринку це" in prompt
    assert "не пиши вступ як для сайту" in prompt
    assert "жодного нового факту" in prompt


def test_weights_are_defined_as_like_plus_fire_minus_dislike():
    row = _feedback(title="same useful story", likes=1, fires=1, dislikes=1)
    assert rc51._feedback_signal(row) == 1.0
