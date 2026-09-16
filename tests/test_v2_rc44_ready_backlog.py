from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.domain import Decision, Stage
from telegram_autopilot.v2.ready_backlog import (
    ReadyBacklogRuntimeEngine,
    ReadyBacklogStore,
    ReadyBacklogSupervisor,
)
from telegram_autopilot.v2.storage import now_iso


def _seed_ready(store: ReadyBacklogStore, *, article_id: int = 1, hours_old: int = 72) -> None:
    stamp = now_iso()
    old = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).astimezone().isoformat(timespec="seconds")
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,enabled,max_age_hours,created_at,updated_at) VALUES(1,'test','',1,24,?,?)",
            (stamp, stamp),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority) VALUES(1,1,'rss','src','https://example.com/feed',1,1,100)"
        )
        con.execute(
            """INSERT INTO articles(
                   id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                   source_published_at,discovered_at,stage,decision,blocked_by,ready_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                article_id, 1, 1, 'item-1', 'title', 'https://example.com/a', 'https://example.com/a', 'body',
                old, old, str(Stage.READY), str(Decision.PUBLISH), 'NONE', old,
            ),
        )
        con.execute(
            """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at)
               VALUES(1,1,'process','WAITING',100,?,?,?)""",
            (stamp, stamp, stamp),
        )


def test_stale_ready_is_archived_by_channel_ttl(tmp_path) -> None:
    store = ReadyBacklogStore(tmp_path / 'v2.sqlite3')
    _seed_ready(store)

    changed = store.expire_stale_ready(1, 24)
    assert changed == 1

    row = store.get_article(1)
    assert row is not None
    assert str(row['stage']) == str(Stage.ARCHIVED)
    assert str(row['decision']) == str(Decision.REJECT)
    assert str(row['blocked_by']) == 'NONE'
    assert str(row['last_error_code']) == 'STALE_READY_MAX_AGE'
    with store.connect() as con:
        job = con.execute("SELECT state,error_code FROM jobs WHERE article_id=1").fetchone()
    assert job is not None
    assert str(job['state']) == 'DONE'
    assert str(job['error_code']) == 'STALE_READY_MAX_AGE'


def test_fresh_ready_is_not_expired(tmp_path) -> None:
    store = ReadyBacklogStore(tmp_path / 'v2.sqlite3')
    _seed_ready(store, hours_old=2)
    assert store.expire_stale_ready(1, 24) == 0
    row = store.get_article(1)
    assert row is not None
    assert str(row['stage']) == str(Stage.READY)


def test_ready_media_recovery_is_narrow_and_fresh_only() -> None:
    source = inspect.getsource(ReadyBacklogStore.insert_collected)
    recovery = inspect.getsource(ReadyBacklogStore._recover_ready_media_blocker)
    assert '_media_json_count(fresh_media) > 0' in source
    assert '_RECOVERABLE_READY_MEDIA_CODES' in recovery
    assert 'media_bundle_complete' in recovery
    assert 'BlockedBy.MEDIA' in recovery
    assert 'BlockedBy.NONE' in recovery


def test_runtime_extends_existing_ttl_cadence() -> None:
    source = inspect.getsource(ReadyBacklogRuntimeEngine._maybe_expire_stale)
    assert 'super()._maybe_expire_stale' in source
    assert 'expire_stale_ready' in source
    assert 'current == previous' in source


def test_supervisor_exposes_ready_blockers_without_remote_agent() -> None:
    source = inspect.getsource(ReadyBacklogSupervisor.build_snapshot)
    assert 'ready_blockers' in source
    assert 'ready_publishable' in source
    assert 'ready_permanent_blocked' in source
    assert 'remote' not in source.casefold()
