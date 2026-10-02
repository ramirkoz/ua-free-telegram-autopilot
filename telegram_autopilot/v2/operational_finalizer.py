from __future__ import annotations

import sqlite3

from .loghub import event

RETENTION_DAYS = 7
_INSTALLED = False


def _purge_expired_materials(store, *, retention_days: int = RETENTION_DAYS) -> dict[str, int]:
    """Keep only the operator's seven-day working set in the live article database."""
    days = max(1, int(retention_days))
    modifier = f"-{days} days"
    stats = {
        "articles_purged": 0,
        "duplicate_links_detached": 0,
        "audit_pruned": 0,
        "vacuumed_after_purge": 0,
    }
    expired_predicate = """datetime(
        CASE
          WHEN stage='PUBLISHED' AND published_at<>'' THEN published_at
          WHEN source_published_at<>'' THEN source_published_at
          ELSE discovered_at
        END
    ) < datetime('now', ?)"""
    with store.connect() as con:
        con.execute(
            "UPDATE channels SET published_dedupe_window_hours=MIN(published_dedupe_window_hours, ?), updated_at=datetime('now') "
            "WHERE published_dedupe_window_hours>?",
            (days * 24, days * 24),
        )
        before = int(con.execute("SELECT COUNT(*) FROM articles").fetchone()[0] or 0)

        # `articles.duplicate_of` is a self-referencing foreign key without
        # ON DELETE SET NULL in existing databases. A recent duplicate may
        # legitimately point at an older canonical article. Detach those
        # historical links before deleting the expired parents so startup
        # retention cannot fail with FOREIGN KEY constraint failed.
        cur = con.execute(
            f"""UPDATE articles
                   SET duplicate_of=NULL
                 WHERE duplicate_of IN (
                     SELECT id FROM articles WHERE {expired_predicate}
                 )""",
            (modifier,),
        )
        stats["duplicate_links_detached"] = max(0, int(cur.rowcount or 0))

        con.execute(f"DELETE FROM articles WHERE {expired_predicate}", (modifier,))
        after = int(con.execute("SELECT COUNT(*) FROM articles").fetchone()[0] or 0)
        stats["articles_purged"] = max(0, before - after)
        cur = con.execute("DELETE FROM audit_events WHERE datetime(created_at)<datetime('now',?)", (modifier,))
        stats["audit_pruned"] = max(0, int(cur.rowcount))
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_working_set ON articles(discovered_at DESC,id DESC)")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_review_working_set "
            "ON articles(discovered_at DESC,id DESC) WHERE final_text<>'' AND stage<>'PUBLISHED'"
        )
        con.execute("ANALYZE")
        con.execute("PRAGMA optimize")
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        page_count = int(con.execute("PRAGMA page_count").fetchone()[0] or 0)
        freelist = int(con.execute("PRAGMA freelist_count").fetchone()[0] or 0)
        page_size = int(con.execute("PRAGMA page_size").fetchone()[0] or 4096)

    reclaim_ratio = (freelist / page_count) if page_count else 0.0
    db_bytes = page_count * page_size
    if stats["articles_purged"] and db_bytes >= 16 * 1024 * 1024 and reclaim_ratio >= 0.10:
        with store.connect() as con:
            con.execute("VACUUM")
            con.execute("ANALYZE")
            con.execute("PRAGMA optimize")
        stats["vacuumed_after_purge"] = 1
    event("storage", "RC103 seven-day live DB purge", **stats)
    return stats


def _install_store_finalizer() -> None:
    from .hardened_storage import HardenedV2Store

    original = HardenedV2Store.run_startup_maintenance

    def run_startup_maintenance(self):
        stats = dict(original(self))
        stats.update(_purge_expired_materials(self))
        return stats

    HardenedV2Store.run_startup_maintenance = run_startup_maintenance


def _install_visible_tab_refresh() -> None:
    """Stop rebuilding every hidden Tk tree every 2.5 seconds."""
    from .ui import MainWindow

    tab_order = (
        "home", "channels", "queue", "editorial", "history", "ai",
        "facebook", "learning", "supervisor", "migration", "logs",
    )
    refreshers = {
        "channels": "refresh_channels",
        "queue": "refresh_queue",
        "editorial": "refresh_editorial_review",
        "history": "refresh_history",
        "ai": "refresh_ai",
        "learning": "refresh_learning",
        "supervisor": "refresh_supervisor",
    }

    def _refresh_active_tab(self) -> None:
        try:
            index = int(self.book.index(self.book.select()))
            key = tab_order[index] if 0 <= index < len(tab_order) else "home"
        except Exception:
            key = "home"
        if key == "home":
            return
        method_name = refreshers.get(key)
        if method_name:
            getattr(self, method_name)()

    def refresh_all(self):
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None
        try:
            self.refresh_home()
            self._refresh_active_tab()
        finally:
            if self.winfo_exists():
                self._refresh_after_id = self.after(2500, self.refresh_all)

    original_init = MainWindow.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            self.book.bind("<<NotebookTabChanged>>", lambda _event: self.after_idle(self._refresh_active_tab), add="+")
        except Exception:
            pass

    MainWindow._refresh_active_tab = _refresh_active_tab
    MainWindow.refresh_all = refresh_all
    MainWindow.__init__ = __init__


def install_operational_finalizer() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_store_finalizer()
    _install_visible_tab_refresh()
    _INSTALLED = True
