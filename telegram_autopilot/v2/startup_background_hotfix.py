from __future__ import annotations

import json
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
_PERIODIC_RETENTION_SECONDS = 1800.0
_MAX_BATCHES_PER_PASS = 60
_LOCK_RETRY_DELAYS_SECONDS = (15.0, 30.0, 60.0, 120.0)
_INSTALLED = False


def _expired_article_ids(store, *, retention_days: int, limit: int = _BATCH_SIZE) -> list[int]:
    modifier = f"-{max(1, int(retention_days))} days"
    with store.connect() as con:
        # Match the SAME discovery-time cutoff used by supervisor's
        # stale_unpublished_over_7d metric. Historical source timestamps can be
        # missing, malformed or future-dated; they must not make obsolete
        # operational rows immortal.
        rows = con.execute(
            """SELECT a.id FROM articles a
                 WHERE datetime(a.discovered_at) < datetime('now', ?)
                   AND NOT EXISTS (
                     SELECT 1 FROM publication_delivery_journal j
                      WHERE j.article_id=a.id AND j.state<>'COMMITTED'
                   )
                 ORDER BY a.id ASC LIMIT ?""",
            (modifier, max(1, int(limit))),
        ).fetchall()
    return [int(row[0]) for row in rows]


def _purge_article_batch(store, article_ids: list[int], *, retention_days: int = OPERATIONAL_RETENTION_DAYS) -> tuple[int, int]:
    if not article_ids:
        return 0, 0
    marks = ",".join("?" for _ in article_ids)
    # Atomic detach+delete: no partially broken duplicate pointers when a
    # concurrent worker or migration writes at the same time. Keep writer lock
    # under 1.5 seconds; retry in the next background cycle if DB is busy.
    with store.transaction() as con:
        con.execute("PRAGMA busy_timeout=1500")
        try:
            con.execute("BEGIN IMMEDIATE")
            eligible = [
                int(row[0]) for row in con.execute(
                    f"""SELECT a.id FROM articles a WHERE a.id IN ({marks})
                           AND datetime(a.discovered_at)<datetime('now',?)
                           AND NOT EXISTS (
                             SELECT 1 FROM publication_delivery_journal j
                              WHERE j.article_id=a.id AND j.state<>'COMMITTED'
                           )""",
                    (*tuple(article_ids), f"-{max(1, int(retention_days))} days"),
                ).fetchall()
            ]
            if not eligible:
                con.rollback()
                return 0, 0
            eligible_marks = ",".join("?" for _ in eligible)
            cur = con.execute(
                f"UPDATE articles SET duplicate_of=NULL WHERE duplicate_of IN ({eligible_marks})",
                tuple(eligible),
            )
            detached = max(0, int(cur.rowcount or 0))
            # The existing BEFORE DELETE trigger archives COMMITTED receipts
            # before the delivery journal cascades. UNKNOWN/FAILED/SENDING rows
            # never become eligible for deletion.
            cur = con.execute(
                f"DELETE FROM articles WHERE id IN ({eligible_marks})", tuple(eligible)
            )
            deleted = max(0, int(cur.rowcount or 0))
            con.commit()
        except Exception:
            con.rollback()
            raise
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

    # Dedupe window and all operator channel settings remain untouched.
    # Historical published-identity snapshots live in separate durable tables.
    for _ in range(_MAX_BATCHES_PER_PASS):
        ids = _expired_article_ids(store, retention_days=days, limit=_BATCH_SIZE)
        if not ids:
            break
        deleted, detached = _purge_article_batch(store, ids, retention_days=days)
        stats["articles_purged"] += deleted
        stats["duplicate_links_detached"] += detached
        stats["batches"] += 1
        event("storage", "RC103 deferred retention batch", batch=stats["batches"], articles_purged=deleted, duplicate_links_detached=detached)
        if deleted == 0:
            break
        time.sleep(0.20)

    stats["audit_pruned"] = _prune_audit_batches(store, retention_days=days)

    # Distinguish genuine cleanup backlog from protected uncertain deliveries.
    with store.connect() as con:
        stats["remaining_eligible"] = int(con.execute(
            """SELECT COUNT(*) FROM articles a
                WHERE datetime(a.discovered_at)<datetime('now',?)
                  AND NOT EXISTS (
                    SELECT 1 FROM publication_delivery_journal j
                     WHERE j.article_id=a.id AND j.state<>'COMMITTED'
                  )""",
            (f"-{days} days",),
        ).fetchone()[0] or 0)
        stats["protected_uncertain"] = int(con.execute(
            """SELECT COUNT(*) FROM articles a
                JOIN publication_delivery_journal j ON j.article_id=a.id
               WHERE datetime(a.discovered_at)<datetime('now',?)
                 AND j.state<>'COMMITTED'""",
            (f"-{days} days",),
        ).fetchone()[0] or 0)
        con.execute(
            """INSERT INTO meta(key,value) VALUES('retention_246_last_run_json',?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (json.dumps(stats, ensure_ascii=False, separators=(",", ":")),),
        )

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


def _periodic_retention_worker(store) -> None:
    # Startup remains fast, and maintenance repeats when the user leaves
    # Autopilot on for days. No daemon-wide VACUUM and no remote DB controls.
    while True:
        _run_deferred_worker(store)
        time.sleep(_PERIODIC_RETENTION_SECONDS)


def _schedule_deferred_maintenance(store) -> bool:
    if bool(getattr(store, "_rc103_deferred_maintenance_started", False)):
        return False
    setattr(store, "_rc103_deferred_maintenance_started", True)
    threading.Thread(target=_periodic_retention_worker, args=(store,), name="V2-246-Periodic-DB-Maintenance", daemon=True).start()
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
            "periodic_retention_seconds": int(_PERIODIC_RETENTION_SECONDS),
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
