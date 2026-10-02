from __future__ import annotations

import json

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2.migration_repair import repair_polling_baseline
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.runtime_hardening import HardenedReadyStore


def _seed_channel(store: HardenedReadyStore, channel_id: int, *, profile: str = "standard", mode: str = "editorial") -> None:
    stamp = "2026-09-28T09:00:00+03:00"
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,channel_mode,editorial_runtime_profile,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (channel_id, f"channel-{channel_id}", f"@channel{channel_id}", mode, profile, stamp, stamp),
        )
        con.execute(
            "INSERT INTO channel_policies(channel_id,updated_at) VALUES(?,?)",
            (channel_id, stamp),
        )


def _add_source(store: HardenedReadyStore, channel_id: int, name: str, url: str, *, priority: int = 100) -> int:
    with store.connect() as con:
        cur = con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(?,?,?,?,1,?)",
            (channel_id, "page", name, url, priority),
        )
        return int(cur.lastrowid)


def test_rc101_commercial_profile_startup_repair_does_not_mutate_operator_config(tmp_path) -> None:
    store = HardenedReadyStore(tmp_path / "rc101.sqlite3")
    _seed_channel(store, 2, profile="commercial_editorial")
    creative_id = _add_source(store, 2, "Creative Boom", "https://creative.example/", priority=100)
    retail_id = _add_source(store, 2, "Modern Retail", "https://retail.example/", priority=100)
    custom_id = _add_source(store, 2, "My Custom Source", "https://custom.example/", priority=77)
    with store.connect() as con:
        con.execute(
            "UPDATE channel_policies SET purpose='OPERATOR PURPOSE',audience='OPERATOR AUDIENCE',selection_rules='KEEP',rejection_rules='KEEP OUT' WHERE channel_id=2"
        )

    result = repair_polling_baseline(store)
    assert result["commercial_profile"] == {"channels": 0, "sources_disabled": 0, "sources_prioritized": 0}

    channel = store.get_channel(2)
    assert channel is not None
    assert channel.policy.purpose == "OPERATOR PURPOSE"
    assert channel.policy.audience == "OPERATOR AUDIENCE"
    assert channel.policy.selection_rules == "KEEP"
    assert channel.policy.rejection_rules == "KEEP OUT"

    with store.connect() as con:
        creative = con.execute("SELECT enabled,priority FROM sources WHERE id=?", (creative_id,)).fetchone()
        retail = con.execute("SELECT enabled,priority FROM sources WHERE id=?", (retail_id,)).fetchone()
        custom = con.execute("SELECT enabled,priority FROM sources WHERE id=?", (custom_id,)).fetchone()
    assert int(creative["enabled"]) == 1 and int(creative["priority"]) == 100
    assert int(retail["enabled"]) == 1 and int(retail["priority"]) == 100
    assert int(custom["enabled"]) == 1 and int(custom["priority"]) == 77


def test_strip_body_links_no_longer_suppresses_source_media(tmp_path) -> None:
    store = HardenedReadyStore(tmp_path / "media.sqlite3")
    _seed_channel(store, 3, mode="monitoring")
    source_id = _add_source(store, 3, "Telegram source", "https://t.me/example")
    store.set_source_strip_body_links(source_id, True)
    media = encode_media("image", "https://example.com/photo.jpg")
    layout = json.dumps(
        {
            "source_kind": "telegram",
            "blocks": [{"type": "media", "kind": "image", "url": "https://example.com/photo.jpg"}],
            "telegram": {"message_ids": ["100"], "media_count": 1, "media_filter_version": 7},
        },
        ensure_ascii=False,
    )
    article_id = store.insert_collected(
        channel_id=3,
        source_id=source_id,
        external_id="example/100",
        title="Тест",
        source_url="https://t.me/example/100",
        raw_text="Текст https://junk.example/cta",
        content_hash="rc98-media",
        source_published_at="2026-09-28T09:00:00+03:00",
        media_json=json.dumps([media]),
        article_layout_json=layout,
    )
    article = store.get_article(article_id)
    assert article is not None
    assert json.loads(str(article["media_json"])) == [media]
    assert store.source_strip_body_links(source_id) is True


def test_first_impact_report_rejected_but_settled_summary_allowed(tmp_path) -> None:
    store = HardenedReadyStore(tmp_path / "monitoring.sqlite3")
    _seed_channel(store, 3, mode="monitoring")
    with store.connect() as con:
        con.execute(
            "UPDATE channel_policies SET rejection_rules=? WHERE channel_id=3",
            ("[LIVE_NOW_RC96] reject live now",),
        )
    channel = store.get_channel(3)
    assert channel is not None

    first = {
        "title": "У місті зафіксовано влучання",
        "raw_text": "Під ранок зафіксовано влучання по об'єкту. Інформація уточнюється.",
    }
    settled = {
        "title": "ОВА повідомила підсумки нічної атаки",
        "raw_text": "За підсумками атаки пошкоджено 12 будинків. Пожежу ліквідовано.",
    }
    assert live_now_exclusion(channel, first)
    assert live_now_exclusion(channel, settled) == ""
