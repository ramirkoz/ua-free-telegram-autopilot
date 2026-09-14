from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2.media_recovery import MediaRecoveryRuntimeEngine as ProductionRuntimeEngine
from telegram_autopilot.v2.media_recovery import MediaRecoveryStore as HardenedV2Store
from telegram_autopilot.v2.strict_ingest import StrictTelegramParser
from telegram_autopilot.v2.media_supervisor import MediaAwareProductionSupervisorService
from telegram_autopilot.v2.supervisor import SupervisorConfig


def _seed_monitoring(store: HardenedV2Store, channel_id: int = 3) -> None:
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(?,?,?,1,'monitoring',?,?)",
            (channel_id, "ЗАПОРІЖЖЯ | ГРОМАДИ", "@gromady", stamp, stamp),
        )
        con.execute(
            "INSERT INTO channel_policies(channel_id,media_policy,updated_at) VALUES(?,'required',?)",
            (channel_id, stamp),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(?,?,'telegram','Громада','https://t.me/community',1,100)",
            (channel_id, channel_id),
        )


def _layout(media_url: str | None = None) -> str:
    blocks = []
    if media_url:
        blocks.append({"type": "media", "kind": "image", "url": media_url})
    return json.dumps(
        {
            "source_kind": "telegram",
            "telegram": {
                "media_filter_version": 4,
                "media_count": 1 if media_url else 0,
                "media_filter": {
                    "raw_candidates": 1,
                    "discarded_non_content": 0 if media_url else 1,
                    "discarded_video_thumb": 0,
                    "discarded_duplicate": 0,
                    "content_media": 1 if media_url else 0,
                },
            },
            "blocks": blocks,
        },
        ensure_ascii=False,
    )


def test_direct_telegram_photo_survives_soft_preview_wrapper() -> None:
    html = """
    <div class="tgme_widget_message" data-post="community/100">
      <a class="tgme_widget_message_user_photo"><img src="https://cdn.example/avatar.jpg"></a>
      <div class="tgme_widget_message_link_preview">
        <a class="tgme_widget_message_photo_wrap js-message_photo" style="background-image:url('https://cdn.example/real.jpg')"></a>
        <i class="link_preview_image" style="background-image:url('https://cdn.example/preview.jpg')"></i>
      </div>
      <div class="tgme_widget_message_text">Новина громади</div>
      <time datetime="2026-09-14T09:00:00+00:00"></time>
    </div>
    """
    parser = StrictTelegramParser("community")
    parser.feed(html)
    parser.close()
    assert len(parser.entries) == 1
    entry = parser.entries[0]
    assert any("real.jpg" in item for item in entry.media)
    assert not any("preview.jpg" in item for item in entry.media)
    assert not any("avatar.jpg" in item for item in entry.media)


def test_archived_media_miss_revives_when_source_refresh_gets_media(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed_monitoring(store)
    aid = store.insert_collected(
        channel_id=3,
        source_id=3,
        external_id="community/100",
        title="Новина",
        source_url="https://t.me/community/100",
        raw_text="body",
        media_json="[]",
        article_layout_json=_layout(None),
    )
    store.update_article(
        aid,
        stage="ARCHIVED",
        decision="REJECT",
        blocked_by="NONE",
        reject_reason="no media",
        last_error_code="MEDIA_REQUIRED_SKIPPED",
        last_error_detail="no media",
    )
    with store.connect() as con:
        con.execute("UPDATE jobs SET state='DONE',error_code='MEDIA_REQUIRED_SKIPPED' WHERE article_id=?", (aid,))

    media = encode_media("image", "https://cdn.example/real.jpg")
    refreshed = store.insert_collected(
        channel_id=3,
        source_id=3,
        external_id="community/100",
        title="Новина",
        source_url="https://t.me/community/100",
        raw_text="body",
        media_json=json.dumps([media]),
        article_layout_json=_layout("https://cdn.example/real.jpg"),
    )
    assert refreshed == aid
    row = store.get_article(aid)
    assert row["stage"] == "COLLECTED"
    assert row["decision"] == "PENDING"
    assert row["last_error_code"] == ""
    assert "real.jpg" in row["media_json"]
    with store.connect() as con:
        job = con.execute("SELECT state FROM jobs WHERE article_id=?", (aid,)).fetchone()
    assert job["state"] == "QUEUED"


def test_required_media_sweeper_waits_for_refresh_grace(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed_monitoring(store)
    aid = store.insert_collected(
        channel_id=3,
        source_id=3,
        external_id="community/102",
        title="Новина",
        source_url="https://t.me/community/102",
        raw_text="body",
        media_json="[]",
        article_layout_json=_layout(None),
    )
    store.update_article(aid, blocked_by="MEDIA", last_error_code="MEDIA_REQUIRED", last_error_detail="waiting")
    with store.connect() as con:
        con.execute("UPDATE jobs SET state='WAITING',error_code='MEDIA_REQUIRED' WHERE article_id=?", (aid,))

    runtime = ProductionRuntimeEngine(store)
    assert runtime._resolve_confirmed_media_misses() == 0
    assert store.get_article(aid)["decision"] == "PENDING"

    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        con.execute("UPDATE articles SET discovered_at=? WHERE id=?", (old, aid))
    assert runtime._resolve_confirmed_media_misses() == 1
    assert store.get_article(aid)["last_error_code"] == "MEDIA_REQUIRED_SKIPPED"


def test_supervisor_detects_media_starvation(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    runtime = SimpleNamespace()
    supervisor = MediaAwareProductionSupervisorService(store, runtime, tmp_path / "logs")
    supervisor._first_seen["MEDIA_STARVATION_3"] = time.time() - 121
    snapshot = {
        "expected_running": True,
        "runtime_running": True,
        "live_workers": 3,
        "live_collectors": 3,
        "runtime_started_at": (datetime.now(timezone.utc) - timedelta(hours=1)).astimezone().isoformat(timespec="seconds"),
        "enabled_channels": {"3": "ЗАПОРІЖЖЯ | ГРОМАДИ"},
        "channels": {"3": {"alive": True, "collector_alive": True, "heartbeat_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}},
        "queue": {"active": 0, "due": 0, "blockers": {}},
        "ai": {"healthy": 1, "total": 1},
        "providers": [],
        "database": {"ok": True, "detail": "ok"},
        "disk": {"free_mb": 999999},
        "operational_states": {"3": {"state": "HEALTHY", "reasons": []}},
        "channel_stats": {
            "3": {
                "name": "ЗАПОРІЖЖЯ | ГРОМАДИ",
                "due_jobs": 0,
                "published_60m": 0,
                "media_required_60m": 13,
                "telegram_raw_candidates_60m": 835,
                "telegram_content_media_60m": 0,
                "sources_total": 49,
                "recent_source_errors_15m": 0,
            }
        },
        "media": {"lost_last_60m": 0, "items": []},
    }
    incidents = supervisor.evaluate(snapshot, SupervisorConfig())
    assert any(item.code == "MEDIA_STARVATION_3" for item in incidents)
