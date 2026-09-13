from __future__ import annotations

import json
from pathlib import Path

import pytest

from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.strict_ingest import StrictTelegramParser, strict_stitch_telegram
from telegram_autopilot.v2.hardened_storage import HardenedV2Store
from telegram_autopilot.v2.update_protocol import UPDATE_RUNTIME_ABI, UpdateProtocol


def _seed_channel(store: HardenedV2Store, channel_id: int, mode: str = "editorial") -> None:
    from telegram_autopilot.v2.storage import now_iso
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(?,?,?,1,?,?,?)",
            (channel_id, f"C{channel_id}", f"@c{channel_id}", mode, stamp, stamp),
        )
        con.execute(
            "INSERT INTO channel_policies(channel_id,updated_at) VALUES(?,?)",
            (channel_id, stamp),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(?,?, 'rss', ?, ?, 1, 100)",
            (channel_id, channel_id, f"S{channel_id}", f"https://source{channel_id}.example/feed"),
        )


def test_editorial_contract_is_exactly_one_media(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed_channel(store, 1, "editorial")
    article_id = store.insert_collected(
        channel_id=1, source_id=1, external_id="x", title="x", source_url="https://source.example/x",
        raw_text="body", media_json=json.dumps([
            "https://cdn.example/hero.jpg", "https://cdn.example/banner.jpg"
        ]),
    )
    row = store.get_article(article_id)
    assert json.loads(row["media_json"]) == ["https://cdn.example/hero.jpg"]


def test_monitoring_preserves_gallery(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed_channel(store, 2, "monitoring")
    article_id = store.insert_collected(
        channel_id=2, source_id=2, external_id="x", title="x", source_url="https://source.example/x",
        raw_text="body", media_json=json.dumps([
            "https://cdn.example/one.jpg", "https://cdn.example/two.jpg"
        ]),
    )
    row = store.get_article(article_id)
    assert len(json.loads(row["media_json"])) == 2


def test_telegram_parser_uses_exact_post_boundary_not_brittle_wrapper_allowlist() -> None:
    html = """
    <div class="tgme_widget_message" data-post="sourcechan/100">
      <a class="tgme_widget_message_user_photo"><img src="https://cdn.example/avatar.jpg"></a>
      <div class="site_logo"><img src="https://cdn.example/logo.jpg"></div>
      <div class="telegram-new-unknown-media-wrapper" style="background-image:url('https://cdn.example/story.jpg')"></div>
      <div class="tgme_widget_message_text">Справжній текст поста</div>
      <time datetime="2026-09-13T09:00:00+00:00"></time>
    </div>
    """
    parser = StrictTelegramParser("sourcechan")
    parser.feed(html)
    parser.close()
    assert len(parser.entries) == 1
    entry = parser.entries[0]
    assert len(entry.media) == 1
    assert "story.jpg" in entry.media[0]
    assert entry.discarded_non_content >= 2


def test_telegram_neighbour_media_is_never_stitched() -> None:
    orphan = TelegramEntry(
        post="sourcechan/100", text="", published="2026-09-13T09:00:00+00:00",
        media=["https://cdn.example/left-channel.jpg"],
    )
    text = TelegramEntry(
        post="sourcechan/101", text="Текст наступного поста", published="2026-09-13T09:00:30+00:00",
        media=[],
    )
    items = strict_stitch_telegram("sourcechan", [orphan, text])
    assert len(items) == 1
    assert items[0].external_id == "sourcechan/101"
    assert items[0].media_urls == []
    layout = json.loads(items[0].article_layout_json)
    assert layout["telegram"]["message_ids"] == ["101"]
    assert layout["telegram"]["stitched"] is False
    assert layout["telegram"]["media_filter_version"] == 4


def test_pre_rc19_telegram_snapshot_is_quarantined(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed_channel(store, 3, "monitoring")
    article_id = store.insert_collected(
        channel_id=3, source_id=3, external_id="tg", title="tg", source_url="https://t.me/source/10",
        raw_text="text", media_json=json.dumps(["https://cdn.example/avatar.jpg"]),
        article_layout_json=json.dumps({
            "source_kind": "telegram",
            "telegram": {"media_filter_version": 2, "media_count": 1},
            "blocks": [{"type": "media", "kind": "image", "url": "https://cdn.example/avatar.jpg"}],
        }),
    )
    store.update_article(article_id, stage="READY", decision="PUBLISH", final_text="stale ready text")
    with store.connect() as con:
        con.execute("UPDATE jobs SET state='DONE' WHERE article_id=?", (article_id,))
    stats = store.run_startup_maintenance()
    row = store.get_article(article_id)
    assert stats["sanitized_telegram_media_v3"] >= 1
    assert json.loads(row["media_json"]) == []
    assert row["stage"] == "COLLECTED" and row["decision"] == "PENDING"
    assert row["last_error_code"] == "TELEGRAM_MEDIA_REFRESH_REQUIRED"
    with store.connect() as con:
        job = con.execute("SELECT state FROM jobs WHERE article_id=?", (article_id,)).fetchone()
    assert job["state"] == "WAITING"


def test_web_media_refresh_replaces_instead_of_accumulating(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed_channel(store, 4, "monitoring")
    article_id = store.insert_collected(
        channel_id=4, source_id=4, external_id="web", title="web", source_url="https://source.example/web",
        raw_text="body", media_json=json.dumps(["https://cdn.example/old-banner.jpg"]),
    )
    store.insert_collected(
        channel_id=4, source_id=4, external_id="web", title="web", source_url="https://source.example/web",
        raw_text="body", media_json=json.dumps(["https://cdn.example/new-hero.jpg"]),
    )
    assert json.loads(store.get_article(article_id)["media_json"]) == ["https://cdn.example/new-hero.jpg"]
    store.insert_collected(
        channel_id=4, source_id=4, external_id="web", title="web", source_url="https://source.example/web",
        raw_text="body", media_json="[]",
    )
    assert json.loads(store.get_article(article_id)["media_json"]) == ["https://cdn.example/new-hero.jpg"]


def test_update_protocol_accepts_only_version_and_hash(tmp_path: Path) -> None:
    protocol = UpdateProtocol(tmp_path / "updates")
    request = protocol.validate_request({
        "request_id": "request-1234",
        "target_version": "2.0.0-rc23",
        "sha256": "a" * 64,
        "source": "agent",
        "url": "https://evil.example/payload.zip",
        "command": "powershell whoami",
    })
    assert request.release_url == (
        "https://github.com/ramirkoz/ua-free-telegram-autopilot/releases/download/"
        "v2.0.0-rc23/UA_FREE_Telegram_Autopilot_v2.0.0-rc23_Update.zip"
    )
    assert protocol.request_is_newer(request)
    assert UPDATE_RUNTIME_ABI == "py312-v1"
    with pytest.raises(ValueError, match="UPDATE_VERSION_INVALID"):
        protocol.validate_request({"target_version": "https://evil.example", "sha256": "a" * 64})
    with pytest.raises(ValueError, match="UPDATE_SHA256_INVALID"):
        protocol.validate_request({"target_version": "2.0.0-rc23", "sha256": "not-a-hash"})


def test_database_backup_is_consistent(tmp_path: Path) -> None:
    import sqlite3

    store = HardenedV2Store(tmp_path / "Data" / "telegram_autopilot_v2.sqlite3")
    protocol = UpdateProtocol(tmp_path / "Data" / "updates")
    request = protocol.validate_request({
        "request_id": "backup-test-1",
        "target_version": "2.0.0-rc21",
        "sha256": "b" * 64,
    })
    backup = protocol.backup_database(store, request)
    assert backup.is_file()
    with sqlite3.connect(backup) as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_update_zip_rejects_path_traversal(tmp_path: Path) -> None:
    import zipfile
    from telegram_autopilot.v2.updater_helper import _safe_extract

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "bad")
    with pytest.raises(RuntimeError, match="UNSAFE_UPDATE_PATH"):
        _safe_extract(archive, tmp_path / "stage")
    assert not (tmp_path / "escape.txt").exists()
