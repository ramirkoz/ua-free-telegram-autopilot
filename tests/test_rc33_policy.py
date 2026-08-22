from __future__ import annotations

from pathlib import Path

from telegram_autopilot.database import Database
from telegram_autopilot.models import CollectedArticle
from telegram_autopilot.rc33_policy import (
    editorial_gate_reason,
    install_rc33_policy,
    media_first_fields,
    normalize_priority,
    output_refusal_blockers,
    split_video_footer,
)


install_rc33_policy()


def _channel(db: Database) -> int:
    return db.save_channel(
        channel_id=None,
        name="CTRL+UA",
        telegram_chat_id="@ctrlua",
        editorial_profile="",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
    )


def test_source_priority_persists_and_orders_collection(tmp_path: Path) -> None:
    db = Database(tmp_path / "autopilot.db")
    channel_id = _channel(db)
    high_id = db.save_source(
        source_id=None, channel_id=channel_id, kind="rss",
        name="High", url="https://high.example/feed", enabled=True, priority=95,
    )
    low_id = db.save_source(
        source_id=None, channel_id=channel_id, kind="rss",
        name="Low", url="https://low.example/feed", enabled=True, priority=20,
    )

    sources = db.list_sources(channel_id)
    assert [s.id for s in sources] == [high_id, low_id]
    assert [s.priority for s in sources] == [95, 20]

    low = next(s for s in sources if s.id == low_id)
    high = next(s for s in sources if s.id == high_id)
    # Insert High first and Low second. Plain "newest first" would now pick Low;
    # RC33 must still process the higher-priority source first.
    db.insert_collected(
        high,
        CollectedArticle(
            external_id="high-1", title="High priority chip launch",
            url="https://high.example/1",
            raw_text="A semiconductor company announced a new chip architecture for data centers. " * 5,
        ),
        baseline=False,
    )
    db.insert_collected(
        low,
        CollectedArticle(
            external_id="low-1", title="Low priority AI launch",
            url="https://low.example/1",
            raw_text="A company announced an artificial intelligence platform for enterprise developers. " * 5,
        ),
        baseline=False,
    )
    pending = db.pending_articles(channel_id, limit=10)
    assert int(pending[0]["source_id"]) == high_id
    assert int(pending[0]["source_priority"]) == 95


def test_priority_validation() -> None:
    assert normalize_priority("100") == 100
    assert normalize_priority(1) == 1
    for bad in (0, 101, "abc", ""):
        try:
            normalize_priority(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"priority {bad!r} must fail")


def test_ctrl_ua_gate_rejects_reddit_captcha_and_fluff() -> None:
    reddit = {
        "title": "AI reaches out",
        "url": "https://www.reddit.com/r/singularity/comments/abc",
        "raw_text": "Prove your humanity. Complete the security verification to continue. " * 6,
        "source_priority": 100,
    }
    assert "Reddit" in editorial_gate_reason(reddit)

    raccoons = {
        "title": "Baby raccoons wrestle on new wildlife cameras",
        "url": "https://example.com/raccoons",
        "raw_text": (
            "A wildlife center installed more cameras around an enclosure. "
            "Young raccoons wrestled, climbed and explored while staff watched remotely. "
            "The center says the animals will later return to the wild. "
        ) * 4,
        "source_priority": 70,
    }
    assert "Cute/pet/wildlife" in editorial_gate_reason(raccoons)


def test_ctrl_ua_gate_keeps_strong_science_and_enterprise_tech() -> None:
    space_health = {
        "title": "NASA-backed study finds microgravity changes astronaut gut microbiome",
        "url": "https://example.com/space-health",
        "raw_text": (
            "Researchers published a study of astronauts who spent months on the ISS. "
            "The NASA-backed research found changes in the gut microbiome under microgravity "
            "and discusses consequences for long-duration space missions. "
        ) * 4,
        "source_priority": 80,
    }
    assert editorial_gate_reason(space_health) == ""

    chips = {
        "title": "New semiconductor packaging tool targets AI data centers",
        "url": "https://example.com/chips",
        "raw_text": (
            "The company announced a semiconductor packaging system using laser lithography. "
            "The technology targets advanced chip interconnects and AI data center hardware. "
        ) * 5,
        "source_priority": 90,
    }
    assert editorial_gate_reason(chips) == ""


def test_refusal_text_is_a_hard_blocker() -> None:
    text = "У наданому фрагменті немає достатньо перевірених фактів для новинної публікації."
    assert output_refusal_blockers(text)


def test_media_first_and_video_footer_helpers() -> None:
    fields = media_first_fields("sendPhoto", {"caption": "text", "show_caption_above_media": "true"})
    assert fields["show_caption_above_media"] == "false"

    core, video = split_video_footer("Текст поста.\n\n🎬 Відео: https://youtu.be/abc")
    assert core == "Текст поста."
    assert video == "https://youtu.be/abc"

    from telegram_autopilot import telegram

    caption = telegram.build_post_text(
        "Текст поста.\n\n🎬 Відео: https://youtu.be/abc",
        source_url="https://example.com/story",
        include_source_link=True,
        hard_limit=900,
    )
    assert caption == "Текст поста.\n\nДжерело\n\n🎬 Відео: https://youtu.be/abc"
    entities = telegram._source_link_entities(caption, "https://example.com/story")
    assert '"text_link"' in entities
