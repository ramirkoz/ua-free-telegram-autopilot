from __future__ import annotations

import inspect
import sqlite3
from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.hardened_storage import HardenedV2Store
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.startup_background_hotfix import _run_batched_retention


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).astimezone().isoformat(timespec="seconds")


def _seed(store: V2Store) -> None:
    with store.connect() as con:
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,'test','-1001',?,?)",
            (now, now),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','source','https://example.com/feed')"
        )


def _article(store: V2Store, external_id: str, discovered_at: str) -> int:
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,discovered_at)
               VALUES(1,1,?,?,?,?)""",
            (external_id, external_id, f"https://example.com/{external_id}", discovered_at),
        )
        return int(cur.lastrowid)


def test_rc103_startup_gate_never_spawns_retention_worker() -> None:
    source = inspect.getsource(HardenedV2Store.run_startup_maintenance)
    assert "_schedule_deferred_maintenance" not in source
    assert 'deferred_retention_scheduled"] = 0' in source
    assert "_compact_operational_database" not in source
    assert "_purge_expired_materials" not in source
    assert 'con.execute("VACUUM")' not in source

    import telegram_autopilot.v2.startup_background_hotfix as hotfix
    assert hotfix._BACKGROUND_DELAY_SECONDS >= 120.0


def test_rc103_retention_is_scheduled_after_runtime_start() -> None:
    from telegram_autopilot.v2 import main as main_module
    source = inspect.getsource(main_module.main)
    start = source.index("app.start_runtime()")
    schedule = source.index("_schedule_deferred_maintenance(store)")
    assert schedule > start


def test_rc103_live_retention_excludes_broad_lock_operations() -> None:
    import telegram_autopilot.v2.startup_background_hotfix as hotfix
    source = inspect.getsource(hotfix._run_batched_retention)
    assert "wal_checkpoint(" not in source
    assert 'con.execute("CREATE INDEX' not in source
    assert 'con.execute("ANALYZE")' not in source
    assert 'con.execute("VACUUM")' not in source


def test_rc103_deferred_retention_keeps_fk_safe_recent_duplicate(tmp_path) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    _seed(store)
    old_id = _article(store, "old-parent", _ago(9))
    recent_id = _article(store, "recent-duplicate", _ago(1))
    with store.connect() as con:
        con.execute("UPDATE articles SET duplicate_of=? WHERE id=?", (old_id, recent_id))

    stats = _run_batched_retention(store, retention_days=7)

    assert stats["articles_purged"] == 1
    assert stats["duplicate_links_detached"] >= 1
    assert stats["vacuumed"] == 0
    assert store.get_article(old_id) is None
    assert store.get_article(recent_id) is not None
    with store.connect() as con:
        assert con.execute("SELECT duplicate_of FROM articles WHERE id=?", (recent_id,)).fetchone()[0] is None


def test_rc103_deferred_retention_purges_in_multiple_small_batches(tmp_path, monkeypatch) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    _seed(store)
    for index in range(5):
        _article(store, f"old-{index}", _ago(8 + index))

    import telegram_autopilot.v2.startup_background_hotfix as hotfix
    monkeypatch.setattr(hotfix, "_BATCH_SIZE", 2)
    monkeypatch.setattr(hotfix.time, "sleep", lambda *_: None)
    stats = hotfix._run_batched_retention(store, retention_days=7)

    assert stats["articles_purged"] == 5
    assert stats["batches"] == 3


def test_rc103_deferred_worker_retries_database_locked(monkeypatch) -> None:
    import telegram_autopilot.v2.startup_background_hotfix as hotfix

    attempts = {"count": 0}

    def fake_retention(store):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return {"articles_purged": 0}

    monkeypatch.setattr(hotfix, "_BACKGROUND_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(hotfix, "_LOCK_RETRY_DELAYS_SECONDS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(hotfix, "_run_batched_retention", fake_retention)
    monkeypatch.setattr(hotfix.time, "sleep", lambda *_: None)

    hotfix._run_deferred_worker(object())
    assert attempts["count"] == 3
