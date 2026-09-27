from __future__ import annotations

import json

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2 import ingest as base
from telegram_autopilot.v2.runtime_hardening import HardenedReadyStore
from telegram_autopilot.v2.telegram_ingest_policy import stitch_adjacent_telegram_media


def test_adjacent_media_only_message_is_stitched_to_following_text() -> None:
    media = base.TelegramEntry(
        post="vasgromada/100",
        text="",
        published="2026-09-27T12:00:00+00:00",
        media=[encode_media("image", "https://example.test/photo.jpg")],
    )
    text = base.TelegramEntry(
        post="vasgromada/101",
        text="Фахівці громади взяли участь у міжнародному саміті.",
        published="2026-09-27T12:01:00+00:00",
        media=[],
    )

    items = stitch_adjacent_telegram_media("vasgromada", [media, text])

    assert len(items) == 1
    assert items[0].external_id == "vasgromada/101"
    assert len(items[0].media_urls) == 1
    layout = json.loads(items[0].article_layout_json)
    assert layout["telegram"]["stitched"] is True
    assert layout["telegram"]["message_ids"] == ["100", "101"]


def test_non_adjacent_media_is_not_borrowed() -> None:
    media = base.TelegramEntry(
        post="source/100",
        text="",
        published="2026-09-27T10:00:00+00:00",
        media=[encode_media("image", "https://example.test/wrong.jpg")],
    )
    text = base.TelegramEntry(
        post="source/102",
        text="Окрема новина без власного медіа.",
        published="2026-09-27T10:01:00+00:00",
        media=[],
    )

    items = stitch_adjacent_telegram_media("source", [media, text])

    assert len(items) == 1
    assert items[0].external_id == "source/102"
    assert items[0].media_urls == []


def test_existing_take_text_only_source_flag_suppresses_media(tmp_path) -> None:
    store = HardenedReadyStore(tmp_path / "autopilot.sqlite3")
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
            ("monitor", "-1001", 1, "monitoring"),
        )
        channel_id = int(con.execute("SELECT id FROM channels WHERE name='monitor'").fetchone()[0])
        cur = con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(?,?,?,?,1,100)",
            (channel_id, "telegram", "text-only source", "https://t.me/textonly"),
        )
        source_id = int(cur.lastrowid)

    # RC97 deliberately upgrades the already visible "Брати ... тільки текст"
    # checkbox instead of inventing a second competing source flag.
    store.set_source_strip_body_links(source_id, True)
    layout = {
        "source_kind": "telegram",
        "telegram": {"media_count": 1, "media_group": False, "stitched": True},
        "blocks": [{"type": "media", "kind": "image", "url": "https://example.test/photo.jpg"}],
    }
    article_id = store.insert_collected(
        channel_id=channel_id,
        source_id=source_id,
        external_id="textonly/1",
        title="Тест",
        source_url="https://t.me/textonly/1",
        raw_text="Текст матеріалу",
        media_json=json.dumps([encode_media("image", "https://example.test/photo.jpg")]),
        article_layout_json=json.dumps(layout),
    )

    row = store.get_article(article_id)
    assert row is not None
    assert json.loads(str(row["media_json"])) == []
    saved_layout = json.loads(str(row["article_layout_json"]))
    assert saved_layout["source_text_only"] is True
    assert saved_layout["telegram"]["media_count"] == 0
    assert saved_layout["telegram"]["stitch_media_suppressed"] is True
    assert not [b for b in saved_layout["blocks"] if b.get("type") == "media"]
