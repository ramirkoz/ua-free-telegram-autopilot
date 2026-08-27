from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram_autopilot.database import Database
from telegram_autopilot.models import CollectedArticle
from telegram_autopilot import rc48_learning as rc48


def _seed_channel(db: Database, name: str) -> tuple[int, int]:
    channel_id = db.save_channel(
        channel_id=None,
        name=name,
        telegram_chat_id=f"@{name.lower().replace(' ', '_')}",
        editorial_profile="Technology news",
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=10,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
    )
    source_id = db.save_source(
        source_id=None,
        channel_id=channel_id,
        kind="rss",
        name="Test",
        url=f"https://example.com/{channel_id}.xml",
        enabled=True,
    )
    return channel_id, source_id


def _published_article(
    db: Database,
    channel_id: int,
    source_id: int,
    *,
    index: int,
    hours_old: int = 30,
) -> int:
    source = next(item for item in db.list_sources(channel_id) if item.id == source_id)
    article_id = db.insert_collected(
        source,
        CollectedArticle(
            external_id=f"item-{channel_id}-{index}",
            title=f"AI chip story {index}",
            url=f"https://example.com/{channel_id}/{index}",
            raw_text=f"Company {index} released an AI accelerator with new memory architecture.",
        ),
        baseline=False,
    )
    assert article_id is not None
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat(timespec="seconds")
    db.update_article(
        article_id,
        status="published",
        published_at=stamp,
        telegram_message_id=str(1000 + index),
        teaser_text=f"Фінальний пост про AI-чип номер {index}.",
        event_summary=f"AI chip release {index}",
    )
    return int(article_id)


def test_rc48_metric_candidate_uses_latest_due_checkpoint(tmp_path) -> None:
    rc48._install_database_patch()
    db = Database(tmp_path / "autopilot.sqlite3")
    channel_id, source_id = _seed_channel(db, "CTRL UA")
    article_id = _published_article(db, channel_id, source_id, index=1, hours_old=30)

    due = db.rc48_metric_candidates(channel_id)
    assert len(due) == 1
    assert due[0]["article_id"] == article_id
    assert due[0]["checkpoint_hours"] == 24


def test_rc48_memory_activates_on_comparable_history_and_is_channel_local(tmp_path) -> None:
    rc48._install_database_patch()
    db = Database(tmp_path / "autopilot.sqlite3")
    channel_id, source_id = _seed_channel(db, "CTRL UA")
    other_channel, other_source = _seed_channel(db, "PRODANO")

    for index in range(1, 11):
        article_id = _published_article(db, channel_id, source_id, index=index)
        db.rc48_save_metric(
            channel_id=channel_id,
            article_id=article_id,
            telegram_message_id=str(1000 + index),
            checkpoint_hours=24,
            views=1000 + index,
            reactions=index,
            forwards=index // 2,
            replies=0,
        )

    other_article = _published_article(db, other_channel, other_source, index=99)
    db.rc48_save_metric(
        channel_id=other_channel,
        article_id=other_article,
        telegram_message_id="9999",
        checkpoint_hours=24,
        views=999999,
        reactions=999,
        forwards=999,
        replies=999,
    )

    snapshot = db.rc48_memory_snapshot(channel_id, limit=30)
    assert snapshot["active"] is True
    assert snapshot["checkpoint_hours"] == 24
    assert snapshot["count"] == 10
    assert len(snapshot["rows"]) == 10
    assert all(int(row["article_id"]) != other_article for row in snapshot["rows"])
    assert "номер 10" in snapshot["rows"][0]["teaser_text"]


def test_rc48_memory_does_not_influence_before_minimum_sample(tmp_path) -> None:
    rc48._install_database_patch()
    db = Database(tmp_path / "autopilot.sqlite3")
    channel_id, source_id = _seed_channel(db, "CTRL UA")

    for index in range(1, rc48.MIN_MEMORY_POSTS):
        article_id = _published_article(db, channel_id, source_id, index=index)
        db.rc48_save_metric(
            channel_id=channel_id,
            article_id=article_id,
            telegram_message_id=str(1000 + index),
            checkpoint_hours=24,
            views=500,
            reactions=10,
            forwards=1,
            replies=1,
        )

    rc48._ACTIVE_DB = db
    channel = db.get_channel(channel_id)
    block = rc48._format_memory_block(
        channel,
        {"title": "New AI accelerator", "raw_text": "A new AI chip uses a memory architecture."},
        purpose="writing",
    )
    assert block == ""


def test_rc48_prompt_memory_uses_real_posts_as_non_factual_examples(tmp_path) -> None:
    rc48._install_database_patch()
    db = Database(tmp_path / "autopilot.sqlite3")
    channel_id, source_id = _seed_channel(db, "CTRL UA")

    for index in range(1, 11):
        article_id = _published_article(db, channel_id, source_id, index=index)
        db.rc48_save_metric(
            channel_id=channel_id,
            article_id=article_id,
            telegram_message_id=str(1000 + index),
            checkpoint_hours=24,
            views=1000,
            reactions=20 + index,
            forwards=5 + index,
            replies=2,
        )

    rc48._ACTIVE_DB = db
    channel = db.get_channel(channel_id)
    block = rc48._format_memory_block(
        channel,
        {"title": "AI chip with new memory", "raw_text": "New AI accelerator memory architecture."},
        purpose="writing",
    )

    assert "поведінкова редакційна пам'ять" in block
    assert "Фінальний пост каналу" in block
    assert "пересилання" in block
    assert "НЕ використовуй жоден факт з еталонів" in block


def test_rc48_message_metrics_sums_telegram_reactions() -> None:
    class Item:
        def __init__(self, count):
            self.count = count

    class Reactions:
        results = [Item(3), Item(4)]

    class Replies:
        replies = 5

    class Message:
        views = 120
        forwards = 9
        reactions = Reactions()
        replies = Replies()

    assert rc48._message_metrics(Message()) == (120, 9, 7, 5)
