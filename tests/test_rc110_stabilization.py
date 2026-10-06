from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import telegram_autopilot.v2.ai_gateway as gateway_mod
from telegram_autopilot.v2.ai_gateway import AIGateway, PRODUCTION_SLOTS
from telegram_autopilot.v2.provider_api import ProviderReply
from telegram_autopilot.v2.publisher import Publisher
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_channel_source(store: V2Store, *, interval: int = 30) -> int:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                 id,name,telegram_chat_id,enabled,publish_24h,min_publish_interval_minutes,
                 created_at,updated_at
               ) VALUES(1,'T','@t',1,1,?,?,?)""",
            (interval, stamp, stamp),
        )
        return int(con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(1,'page','S','https://example.com',1,100)"
        ).lastrowid)


def test_rc110_http_provider_contract_returns_six_fields(monkeypatch) -> None:
    reply = ProviderReply(
        text="ok",
        model="nvidia/nemotron-3-super-120b-a12b",
        input_tokens=101,
        output_tokens=19,
        total_tokens=120,
    )
    monkeypatch.setattr(gateway_mod, "openai_compatible_chat", lambda *a, **k: reply)
    slot = next(s for s in PRODUCTION_SLOTS if s.provider == "nvidia" and "super" in s.model)
    cfg = SimpleNamespace(
        nvidia_api_key="x",
        groq_api_key="",
        cloudflare_api_token="",
        cloudflare_account_id="",
    )
    out = AIGateway.__new__(AIGateway)._call_slot(
        slot, cfg, "test", max_output_tokens=100, timeout_seconds=10, json_mode=False
    )
    assert len(out) == 6
    assert out[0] == "ok"
    assert out[3:] == (101, 19, 120)


def test_rc110_human_approved_catchup_uses_one_minute_gap(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    source_id = _seed_channel_source(store, interval=30)
    two_minutes_ago = (datetime.now(timezone.utc) - timedelta(minutes=2)).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        con.execute(
            """INSERT INTO articles(
                 channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                 discovered_at,stage,decision,final_text,published_at
               ) VALUES(1,?,'pub','P','https://example.com/p','https://example.com/p','x',?,
                        'PUBLISHED','PUBLISH','published',?)""",
            (source_id, two_minutes_ago, two_minutes_ago),
        )
    pub = Publisher(store)
    assert pub.can_publish_now(1) == (False, "MIN_INTERVAL")
    pub._rc110_human_catchup = True
    assert pub.can_publish_now(1) == (True, "OK")


def test_rc110_reconciles_ghost_nonpending_jobs(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    source_id = _seed_channel_source(store)
    stamp = now_iso()
    with store.connect() as con:
        aid = int(con.execute(
            """INSERT INTO articles(
                 channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                 discovered_at,stage,decision,final_text,ready_at
               ) VALUES(1,?,'ready','R','https://example.com/r','https://example.com/r','x',?,
                        'READY','PUBLISH','ready',?)""",
            (source_id, stamp, stamp),
        ).lastrowid)
        con.execute(
            """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at)
               VALUES(?,1,'process','QUEUED',100,?,?,?)""",
            (aid, stamp, stamp, stamp),
        )
    assert store.reconcile_nonpending_jobs(1) == 1
    with store.connect() as con:
        job = con.execute("SELECT state,error_code FROM jobs WHERE article_id=?", (aid,)).fetchone()
    assert job["state"] == "DONE"
    assert job["error_code"] == "RC110_NONPENDING_RECONCILED"


def test_rc110_403_gets_immediate_long_cooldown(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    source_id = _seed_channel_source(store)
    failures, cooldown = store.record_source_failure(
        source_id, 4500, "Сервер джерела відхилив автоматичний запит (HTTP 403)."
    )
    assert failures == 1
    assert cooldown
    row = store.source_health(source_id)
    assert row is not None
    assert row["last_outcome"] == "HTTP_403"
    assert int(row["failure_count"]) == 1


def test_rc110_slow_success_is_cooled_and_zero_streak_is_tracked(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    source_id = _seed_channel_source(store)
    store.record_source_success(source_id, 130_000, items=10, added=1)
    row = store.source_health(source_id)
    assert row is not None
    assert row["last_outcome"] == "SLOW"
    assert row["cooldown_until"]

    # Clear the slow cooldown and establish repeated empty-but-successful fetches.
    with store.connect() as con:
        con.execute("UPDATE source_health SET cooldown_until='',slow_streak=0 WHERE source_id=?", (source_id,))
    for _ in range(4):
        store.record_source_success(source_id, 1000, items=0, added=0)
    row = store.source_health(source_id)
    assert row["last_outcome"] == "EMPTY"
    assert int(row["zero_result_streak"]) == 4
    assert row["cooldown_until"]
