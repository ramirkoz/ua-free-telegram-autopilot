from __future__ import annotations

import sqlite3

from .storage import V2Store, now_iso


def ensure_editorial_state_schema(store: V2Store) -> None:
    with store.connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS editorial_actions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                action TEXT NOT NULL,title TEXT NOT NULL DEFAULT '',
                before_text TEXT NOT NULL DEFAULT '',after_text TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_editorial_actions_channel_time
                ON editorial_actions(channel_id,created_at DESC,id DESC);
            CREATE INDEX IF NOT EXISTS idx_editorial_actions_article_id
                ON editorial_actions(article_id,id DESC);
            CREATE TABLE IF NOT EXISTS rewrite_revisions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL,origin TEXT NOT NULL DEFAULT 'system',
                reason TEXT NOT NULL DEFAULT '',text TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(article_id,revision)
            );
            CREATE INDEX IF NOT EXISTS idx_rewrite_revisions_article
                ON rewrite_revisions(article_id,revision DESC);
            """
        )


def record_rewrite_revision(
    store: V2Store,
    article_id: int,
    text: str,
    *,
    origin: str = "system",
    reason: str = "",
) -> int:
    value = str(text or "").strip()
    if not value:
        return 0
    ensure_editorial_state_schema(store)
    row = store.get_article(int(article_id))
    if row is None:
        raise KeyError(article_id)
    with store.transaction() as con:
        try:
            con.execute("BEGIN IMMEDIATE")
            current = con.execute(
                "SELECT COALESCE(MAX(revision),0) FROM rewrite_revisions WHERE article_id=?",
                (int(article_id),),
            ).fetchone()
            revision = int(current[0] or 0) + 1
            con.execute(
                """INSERT INTO rewrite_revisions(article_id,channel_id,revision,origin,reason,text,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    int(article_id),
                    int(row["channel_id"]),
                    revision,
                    str(origin)[:40],
                    str(reason)[:240],
                    value,
                    now_iso(),
                ),
            )
            con.commit()
            return revision
        except Exception:
            con.rollback()
            raise


def preserve_current_rewrite(
    store: V2Store,
    article_id: int,
    *,
    origin: str = "system",
    reason: str = "",
) -> int:
    ensure_editorial_state_schema(store)
    row = store.get_article(int(article_id))
    if row is None:
        return 0
    value = str(row["final_text"] or "").strip()
    if not value:
        return 0
    with store.connect() as con:
        last = con.execute(
            "SELECT text FROM rewrite_revisions WHERE article_id=? ORDER BY revision DESC LIMIT 1",
            (int(article_id),),
        ).fetchone()
    if last is not None and str(last[0] or "").strip() == value:
        return 0
    return record_rewrite_revision(store, int(article_id), value, origin=origin, reason=reason)
