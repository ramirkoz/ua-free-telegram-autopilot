from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any

from .loghub import event
from .storage import V2Store
from .operational_retention import OPERATIONAL_RETENTION_DAYS, _apply_scientific_news_profile


_BATCH_SIZE = 100
_AUDIT_BATCH_SIZE = 500
# The live failure proved that a 3-second delay lets retention race runtime startup.
# Five minutes puts all cleanup outside the startup/readiness window even on a slow
# migrated operator database. The worker is daemonized and lock-aware.
_BACKGROUND_DELAY_SECONDS = 300.0
_LOCK_RETRY_DELAYS_SECONDS = (15.0, 30.0, 60.0, 120.0)
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
            ids = [int(row[0]) for row in con.execute(
                "SELECT id FROM audit_events WHERE datetime(created_at)<datetime('now',?) ORDER BY id ASC LIMIT ?",
                (modifier, _AUDIT_BATCH_SIZE),
            ).fetchall()]
            if not ids:
                break
            marks = ",".join("?" for _ in ids)
            cur = con.execute(f"DELETE FROM audit_events WHERE id IN ({marks})", tuple(ids))
            total += max(0, int(cur.rowcount or 0))
        time.sleep(0.10)
    return total


def _run_batched_retention(store, *, retention_days: int = OPERATIONAL_RETENTION_DAYS) -> dict[str, Any]:
    """Prune the seven-day working set in short, lock-friendly batches."""
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

    while True:
        ids = _expired_article_ids(store, retention_days=days, limit=_BATCH_SIZE)
        if not ids:
            break
        deleted, detached = _purge_article_batch(store, ids)
        stats["articles_purged"] += deleted
        stats["duplicate_links_detached"] += detached
        stats["batches"] += 1
        event("storage", "RC103 deferred retention batch", batch=stats["batches"], articles_purged=deleted, duplicate_links_detached=detached)
        if deleted == 0:
            break
        time.sleep(0.20)

    stats["audit_pruned"] = _prune_audit_batches(store, retention_days=days)

    # No live VACUUM/ANALYZE/index creation/forced checkpoint. Those operations can
    # take or wait on broad SQLite locks and are not worth risking operator runtime.
    with store.connect() as con:
        page_count = int(con.execute("PRAGMA page_count").fetchone()[0] or 0)
        freelist = int(con.execute("PRAGMA freelist_count").fetchone()[0] or 0)
        page_size = int(con.execute("PRAGMA page_size").fetchone()[0] or 4096)

    size_bytes = page_count * page_size
    free_ratio = (freelist / page_count) if page_count else 0.0
    stats["size_bytes"] = size_bytes
    stats["freelist_pages"] = freelist
    stats["free_ratio"] = round(free_ratio, 4)
    stats["vacuum_recommended"] = int(size_bytes >= 16 * 1024 * 1024 and free_ratio >= 0.10)
    event("storage", "RC103 deferred seven-day maintenance complete", **stats)
    return stats


def _is_lock_error(exc: BaseException) -> bool:
    text = str(exc or "").casefold()
    return isinstance(exc, sqlite3.OperationalError) and ("locked" in text or "busy" in text)


def _run_deferred_worker(store) -> None:
    time.sleep(_BACKGROUND_DELAY_SECONDS)
    attempts = 0
    while True:
        try:
            stats = _run_batched_retention(store)
            event("app", "RC103 deferred database maintenance complete", **stats)
            return
        except Exception as exc:
            if not _is_lock_error(exc) or attempts >= len(_LOCK_RETRY_DELAYS_SECONDS):
                event("app", "RC103 deferred database maintenance failed", level=40, detail=str(exc)[:1600])
                return
            delay = float(_LOCK_RETRY_DELAYS_SECONDS[attempts])
            attempts += 1
            event("app", "RC103 deferred database maintenance postponed: database busy", level=30, attempt=attempts, retry_in_seconds=delay, detail=str(exc)[:500])
            time.sleep(delay)


def _schedule_deferred_maintenance(store) -> bool:
    if bool(getattr(store, "_rc103_deferred_maintenance_started", False)):
        return False
    setattr(store, "_rc103_deferred_maintenance_started", True)
    threading.Thread(target=_run_deferred_worker, args=(store,), name="V2-RC103-Deferred-DB-Maintenance", daemon=True).start()
    return True


def _install_fast_startup_contract() -> None:
    from .hardened_storage import HardenedV2Store

    def run_startup_maintenance(self):
        # RC103 startup contract: housekeeping can NEVER decide whether the app
        # starts. Full-table URL/media/duplicate repairs are deliberately excluded
        # from the startup path. Only schedule lock-friendly retention for later.
        stats = {
            "startup_gate_bypassed": 1,
            "deferred_retention_scheduled": int(_schedule_deferred_maintenance(self)),
            "deferred_retention_delay_seconds": int(_BACKGROUND_DELAY_SECONDS),
        }
        event("app", "RC103 fast startup gate complete; all DB maintenance deferred", **stats)
        return stats

    HardenedV2Store.run_startup_maintenance = run_startup_maintenance
    HardenedV2Store.run_deferred_operational_maintenance = _run_batched_retention


def install_startup_background_hotfix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_fast_startup_contract()
    _INSTALLED = True
