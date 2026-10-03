from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any

from .loghub import event
from .storage import V2Store
from .operational_retention import OPERATIONAL_RETENTION_DAYS, _apply_scientific_news_profile


_BATCH_SIZE = 200
_AUDIT_BATCH_SIZE = 1000
_BACKGROUND_DELAY_SECONDS = 3.0
_INSTALLED = False


def _expired_article_ids(store, *, retention_days: int, limit: int = _BATCH_SIZE) -> list[int]:
    modifier = f"-{max(1, int(retention_days))} days"
    with store.connect() as con:
        rows = con.execute(
            """SELECT id FROM articles
                 WHERE datetime(
                     CASE
                       WHEN stage='PUBLISHED' AND published_at<>'' THEN published_at
                       WHEN source_published_at<>'' THEN source_published_at
                       ELSE discovered_at
                     END
                 ) < datetime('now', ?)
                 ORDER BY id ASC
                 LIMIT ?""",
            (modifier, max(1, int(limit))),
        ).fetchall()
    return [int(row[0]) for row in rows]


def _purge_article_batch(store, article_ids: list[int]) -> tuple[int, int]:
    if not article_ids:
        return 0, 0
    marks = ",".join("?" for _ in article_ids)
    with store.connect() as con:
        # A surviving recent duplicate can point at an expired parent. Detach every
        # reference to this batch before deleting it so FK enforcement stays on.
        cur = con.execute(
            f"UPDATE articles SET duplicate_of=NULL WHERE duplicate_of IN ({marks})",
            tuple(article_ids),
        )
        detached = max(0, int(cur.rowcount or 0))
        cur = con.execute(f"DELETE FROM articles WHERE id IN ({marks})", tuple(article_ids))
        deleted = max(0, int(cur.rowcount or 0))
    return deleted, detached


def _prune_audit_batches(store, *, retention_days: int) -> int:
    modifier = f"-{max(1, int(retention_days))} days"
    total = 0
    while True:
        with store.connect() as con:
            ids = [
                int(row[0])
                for row in con.execute(
                    "SELECT id FROM audit_events WHERE datetime(created_at)<datetime('now',?) ORDER BY id ASC LIMIT ?",
                    (modifier, _AUDIT_BATCH_SIZE),
                ).fetchall()
            ]
            if not ids:
                break
            marks = ",".join("?" for _ in ids)
            cur = con.execute(f"DELETE FROM audit_events WHERE id IN ({marks})", tuple(ids))
            total += max(0, int(cur.rowcount or 0))
        time.sleep(0.01)
    return total


def _run_batched_retention(store, *, retention_days: int = OPERATIONAL_RETENTION_DAYS) -> dict[str, Any]:
    """Prune the seven-day working set without a startup-blocking VACUUM.

    Work is intentionally split into short autocommit batches. This keeps the live
    runtime and Tk queries from waiting behind one huge DELETE/VACUUM transaction.
    """
    days = max(1, int(retention_days))
    stats: dict[str, Any] = {
        "articles_purged": 0,
        "duplicate_links_detached": 0,
        "audit_pruned": 0,
        "batches": 0,
        "vacuumed": 0,
        "vacuum_recommended": 0,
    }

    with store.connect() as con:
        con.execute(
            "UPDATE channels SET published_dedupe_window_hours=MIN(published_dedupe_window_hours, ?), updated_at=datetime('now') "
            "WHERE published_dedupe_window_hours>?",
            (days * 24, days * 24),
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_discovered_recent ON articles(discovered_at DESC,id DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_review_recent ON articles(stage,discovered_at DESC,id DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_working_set ON articles(discovered_at DESC,id DESC)")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_review_working_set "
            "ON articles(discovered_at DESC,id DESC) WHERE final_text<>'' AND stage<>'PUBLISHED'"
        )

    while True:
        ids = _expired_article_ids(store, retention_days=days, limit=_BATCH_SIZE)
        if not ids:
            break
        deleted, detached = _purge_article_batch(store, ids)
        stats["articles_purged"] += deleted
        stats["duplicate_links_detached"] += detached
        stats["batches"] += 1
        event(
            "storage",
            "RC103 deferred retention batch",
            batch=stats["batches"],
            articles_purged=deleted,
            duplicate_links_detached=detached,
        )
        if deleted == 0:
            break
        time.sleep(0.02)

    stats["audit_pruned"] = _prune_audit_batches(store, retention_days=days)

    with store.connect() as con:
        try:
            con.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
        try:
            con.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.Error:
            pass
        page_count = int(con.execute("PRAGMA page_count").fetchone()[0] or 0)
        freelist = int(con.execute("PRAGMA freelist_count").fetchone()[0] or 0)
        page_size = int(con.execute("PRAGMA page_size").fetchone()[0] or 4096)

    size_bytes = page_count * page_size
    free_ratio = (freelist / page_count) if page_count else 0.0
    stats["size_bytes"] = size_bytes
    stats["freelist_pages"] = freelist
    stats["free_ratio"] = round(free_ratio, 4)
    # Full VACUUM takes an exclusive rewrite lock. Never do it automatically while
    # the runtime is live; logical pruning and PRAGMA optimize deliver the useful win.
    stats["vacuum_recommended"] = int(size_bytes >= 16 * 1024 * 1024 and free_ratio >= 0.10)
    event("storage", "RC103 deferred seven-day maintenance complete", **stats)
    return stats


def _run_deferred_worker(store) -> None:
    time.sleep(_BACKGROUND_DELAY_SECONDS)
    try:
        stats = _run_batched_retention(store)
        event("app", "RC103 deferred database maintenance complete", **stats)
    except Exception as exc:
        event("app", "RC103 deferred database maintenance failed", level=40, detail=str(exc)[:1600])


def _schedule_deferred_maintenance(store) -> bool:
    if bool(getattr(store, "_rc103_deferred_maintenance_started", False)):
        return False
    setattr(store, "_rc103_deferred_maintenance_started", True)
    threading.Thread(
        target=_run_deferred_worker,
        args=(store,),
        name="V2-RC103-Deferred-DB-Maintenance",
        daemon=True,
    ).start()
    return True


def _install_fast_startup_contract() -> None:
    from .hardened_storage import HardenedV2Store

    def run_startup_maintenance(self):
        # Keep the proven pre-RC103 startup repairs in the startup gate. The heavy
        # seven-day purge/compaction added in RC103 is explicitly deferred.
        stats = dict(V2Store.run_startup_maintenance(self))
        stats["sanitized_telegram_media_v3"] = self._sanitize_pre_rc19_telegram_media()
        stats["editorial_media_trimmed"] = self._enforce_editorial_single_media()
        stats["scientific_news_profiles_applied"] = _apply_scientific_news_profile(self)
        stats["deferred_retention_scheduled"] = int(_schedule_deferred_maintenance(self))
        event("app", "RC103 startup gate complete; retention deferred", **stats)
        return stats

    HardenedV2Store.run_startup_maintenance = run_startup_maintenance
    HardenedV2Store.run_deferred_operational_maintenance = _run_batched_retention


def install_startup_background_hotfix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_fast_startup_contract()
    _INSTALLED = True
