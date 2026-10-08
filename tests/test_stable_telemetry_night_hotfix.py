from __future__ import annotations

import inspect
from pathlib import Path

from telegram_autopilot.v2.bounded_ingest import BoundedStrictIngestService
from telegram_autopilot.v2.strict_ingest import StrictIngestService
from telegram_autopilot.v2.storage import V2Store, now_iso
from telegram_autopilot.v2.supervisor import SupervisorService


class _Runtime:
    def health_snapshot(self):
        return {
            "running": False,
            "stop_requested": False,
            "live_workers": 0,
            "live_collectors": 0,
            "started_at": "",
            "channels": {},
            "providers": [],
            "models": [],
        }


def _store(tmp_path: Path) -> V2Store:
    store = V2Store(tmp_path / "stable-hotfix.sqlite3")
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,created_at,updated_at)
               VALUES(1,'Test','@test',1,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority)
               VALUES(1,1,'rss','Healthy feed','https://example.com/feed',1,100)"""
        )
    return store


def test_known_only_source_does_not_enter_empty_cooldown(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for _ in range(12):
        store.record_source_success(1, 4500, items=40, added=0)
    row = store.source_health(1)
    assert row is not None
    assert row["zero_result_streak"] == 0
    assert row["cooldown_until"] == ""
    assert row["last_outcome"] == "KNOWN_ONLY"


def test_true_zero_item_web_source_can_still_enter_bounded_cooldown(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for _ in range(6):
        store.record_source_success(1, 4500, items=0, added=0)
    row = store.source_health(1)
    assert row is not None
    assert row["zero_result_streak"] == 6
    assert row["cooldown_until"]
    assert row["last_outcome"] == "EMPTY"


def test_active_ingest_paths_forward_real_yield_to_source_health() -> None:
    bounded = inspect.getsource(BoundedStrictIngestService.collect_channel)
    strict = inspect.getsource(StrictIngestService.collect_channel)
    expected = "record_source_success(source.id, duration_ms, items=len(items), added=source_added)"
    assert expected in bounded
    assert expected in strict


def test_media_loss_uses_committed_delivery_contract_not_raw_bundle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO articles(
                 id,channel_id,source_id,external_id,title,source_url,canonical_source_url,
                 raw_text,content_hash,discovered_at,stage,decision,blocked_by,published_at,
                 telegram_message_id,telegram_media_count,media_json,article_layout_json
               ) VALUES(10,1,1,'x','Text-only publication','https://example.com/x','https://example.com/x',
                        'body','hash',?,'PUBLISHED','PUBLISH','NONE',?,'100',0,?,'{}')""",
            (stamp, stamp, '["https://cdn.example.com/raw-source-image.jpg"]'),
        )
        con.execute(
            """INSERT INTO publication_delivery_journal(
                 article_id,channel_id,state,mode,complete,expected_media_count,media_count,
                 primary_message_id,message_ids_json,attempt_count,prepared_at,acknowledged_at,committed_at,updated_at
               ) VALUES(10,1,'COMMITTED','text',1,0,0,'100','["100"]',1,?,?,?,?)""",
            (stamp, stamp, stamp, stamp),
        )
    sup = SupervisorService(store, _Runtime(), tmp_path / "logs")
    snap = sup._media_snapshot()
    assert snap["lost_last_60m"] == 0


def test_media_loss_still_detects_real_committed_shortfall(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO articles(
                 id,channel_id,source_id,external_id,title,source_url,canonical_source_url,
                 raw_text,content_hash,discovered_at,stage,decision,blocked_by,published_at,
                 telegram_message_id,telegram_media_count,media_json,article_layout_json
               ) VALUES(11,1,1,'y','Partial publication','https://example.com/y','https://example.com/y',
                        'body','hash2',?,'PUBLISHED','PUBLISH','NONE',?,'101',1,'[]','{}')""",
            (stamp, stamp),
        )
        con.execute(
            """INSERT INTO publication_delivery_journal(
                 article_id,channel_id,state,mode,complete,expected_media_count,media_count,
                 primary_message_id,message_ids_json,attempt_count,prepared_at,acknowledged_at,committed_at,updated_at
               ) VALUES(11,1,'COMMITTED','media_final',1,2,1,'101','["101"]',1,?,?,?,?)""",
            (stamp, stamp, stamp, stamp),
        )
    sup = SupervisorService(store, _Runtime(), tmp_path / "logs")
    snap = sup._media_snapshot()
    assert snap["lost_last_60m"] == 1
    assert snap["items"][0]["article_id"] == 11


def test_feedback_auto_refresh_state_is_in_supervisor_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.connect() as con:
        con.execute("INSERT INTO meta(key,value) VALUES('feedback_auto_refresh_seconds','10800')")
        con.execute("INSERT INTO meta(key,value) VALUES('feedback_auto_refresh_last_success','2026-10-08T06:01:00+03:00')")
        con.execute("INSERT INTO meta(key,value) VALUES('feedback_auto_refresh_last_error','')")
    sup = SupervisorService(store, _Runtime(), tmp_path / "logs")
    snap = sup.build_snapshot()
    assert snap["feedback_auto_refresh"]["interval_seconds"] == 10800
    assert snap["feedback_auto_refresh"]["last_success"] == "2026-10-08T06:01:00+03:00"


def test_feedback_log_is_part_of_drive_recent_events() -> None:
    source = inspect.getsource(SupervisorService._recent_log_events)
    assert '"feedback"' in source
