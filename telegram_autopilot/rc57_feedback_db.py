from __future__ import annotations

import json
import sqlite3
from typing import Any

from .database import now_iso
from .rc57_feedback_model import FeedbackSnapshot

_PATCHED = False


def install_database_patch() -> None:
    global _PATCHED
    if _PATCHED:
        return
    from . import rc51_feedback
    rc51_feedback._install_database_patch()
    from .database import Database
    previous_init = Database._init

    def init_rc57(self):
        previous_init(self)
        with self.connect() as con:
            columns = {str(row[1]) for row in con.execute("PRAGMA table_info(telegram_feedback)").fetchall()}
            additions = (
                ("editor_admin_count", "INTEGER NOT NULL DEFAULT 0"),
                ("editor_reacted_count", "INTEGER NOT NULL DEFAULT 0"),
                ("editor_coverage", "TEXT NOT NULL DEFAULT 'legacy_operator'"),
                ("reactor_scan_complete", "INTEGER NOT NULL DEFAULT 0"),
                ("reactor_scanned", "INTEGER NOT NULL DEFAULT 0"),
                ("audience_reactions_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("audience_total", "INTEGER NOT NULL DEFAULT 0"),
                ("audience_positive", "INTEGER NOT NULL DEFAULT 0"),
                ("audience_negative", "INTEGER NOT NULL DEFAULT 0"),
                ("audience_fires", "INTEGER NOT NULL DEFAULT 0"),
                ("audience_other", "INTEGER NOT NULL DEFAULT 0"),
            )
            for name, declaration in additions:
                if name not in columns:
                    con.execute(f"ALTER TABLE telegram_feedback ADD COLUMN {name} {declaration}")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS telegram_editor_reactions (
                    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                    telegram_message_id TEXT NOT NULL,
                    admin_peer_id TEXT NOT NULL,
                    admin_name TEXT NOT NULL DEFAULT '',
                    checked_at TEXT NOT NULL,
                    likes INTEGER NOT NULL DEFAULT 0,
                    dislikes INTEGER NOT NULL DEFAULT 0,
                    fires INTEGER NOT NULL DEFAULT 0,
                    other_reactions_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(article_id, admin_peer_id)
                );
                CREATE INDEX IF NOT EXISTS idx_editor_reactions_channel_checked
                    ON telegram_editor_reactions(channel_id, checked_at DESC);
                """
            )

    def save_snapshot_batch(self, channel_id: int, snapshots: list[FeedbackSnapshot]) -> None:
        if not snapshots:
            return
        stamp = now_iso()
        con = sqlite3.connect(self.path, timeout=2.0)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=2000")
            for snap in snapshots:
                con.execute(
                    """INSERT INTO telegram_feedback(
                           article_id,channel_id,telegram_message_id,checked_at,published_at,
                           views,forwards,replies,likes,dislikes,fires,other_reactions,
                           editor_admin_count,editor_reacted_count,editor_coverage,
                           reactor_scan_complete,reactor_scanned,audience_reactions_json,
                           audience_total,audience_positive,audience_negative,audience_fires,audience_other
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(article_id) DO UPDATE SET
                           telegram_message_id=excluded.telegram_message_id,checked_at=excluded.checked_at,
                           published_at=excluded.published_at,views=excluded.views,forwards=excluded.forwards,
                           replies=excluded.replies,likes=excluded.likes,dislikes=excluded.dislikes,
                           fires=excluded.fires,other_reactions=excluded.other_reactions,
                           editor_admin_count=excluded.editor_admin_count,editor_reacted_count=excluded.editor_reacted_count,
                           editor_coverage=excluded.editor_coverage,reactor_scan_complete=excluded.reactor_scan_complete,
                           reactor_scanned=excluded.reactor_scanned,audience_reactions_json=excluded.audience_reactions_json,
                           audience_total=excluded.audience_total,audience_positive=excluded.audience_positive,
                           audience_negative=excluded.audience_negative,audience_fires=excluded.audience_fires,
                           audience_other=excluded.audience_other""",
                    (
                        snap.article_id, int(channel_id), snap.telegram_message_id, stamp, snap.published_at,
                        snap.views, snap.forwards, snap.replies, snap.editor_likes, snap.editor_dislikes,
                        snap.editor_fires, snap.editor_other, snap.editor_admin_count, snap.editor_reacted_count,
                        snap.editor_coverage, int(snap.reactor_scan_complete), snap.reactor_scanned,
                        json.dumps(snap.audience_counts, ensure_ascii=False, sort_keys=True), snap.audience_total,
                        snap.audience_positive, snap.audience_negative, snap.audience_fires, snap.audience_other,
                    ),
                )
                con.execute("DELETE FROM telegram_editor_reactions WHERE article_id=?", (snap.article_id,))
                for row in snap.editor_rows:
                    con.execute(
                        """INSERT INTO telegram_editor_reactions(
                               article_id,channel_id,telegram_message_id,admin_peer_id,admin_name,checked_at,
                               likes,dislikes,fires,other_reactions_json
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            snap.article_id, int(channel_id), snap.telegram_message_id,
                            str(row.get("admin_peer_id") or ""), str(row.get("admin_name") or "")[:300], stamp,
                            int(row.get("likes") or 0), int(row.get("dislikes") or 0), int(row.get("fires") or 0),
                            json.dumps(row.get("other") or {}, ensure_ascii=False, sort_keys=True),
                        ),
                    )
            con.commit()
        finally:
            con.close()

    def feedback_rows_rc57(self, channel_id: int, *, days: int = 7, limit: int = 180):
        with self.connect() as con:
            rows = con.execute(
                """SELECT f.*,a.source_id,a.title,a.raw_text,a.event_summary,a.teaser_text
                   FROM telegram_feedback f JOIN articles a ON a.id=f.article_id
                   WHERE f.channel_id=? AND datetime(f.published_at) >= datetime('now', ?)
                     AND (
                         f.likes>0 OR f.dislikes>0 OR f.fires>0
                         OR f.audience_total>0 OR f.forwards>0 OR f.replies>0
                     )
                   ORDER BY datetime(f.published_at) DESC LIMIT ?""",
                (int(channel_id), f"-{max(1, int(days))} days", max(1, min(500, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    def feedback_stats(self, channel_id: int) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                """SELECT COUNT(*) tracked,
                          SUM(CASE WHEN likes>0 OR dislikes>0 OR fires>0 THEN 1 ELSE 0 END) editor_rated_posts,
                          COALESCE(SUM(likes),0) likes,COALESCE(SUM(dislikes),0) dislikes,COALESCE(SUM(fires),0) fires,
                          SUM(CASE WHEN audience_total>0 OR forwards>0 OR replies>0 THEN 1 ELSE 0 END) audience_rated_posts,
                          COALESCE(SUM(audience_total),0) audience_total,COALESCE(SUM(audience_positive),0) audience_positive,
                          COALESCE(SUM(audience_negative),0) audience_negative,COALESCE(SUM(views),0) views,
                          COALESCE(SUM(forwards),0) forwards,COALESCE(MAX(editor_admin_count),0) admin_count,
                          SUM(CASE WHEN editor_coverage='all_admins' AND reactor_scan_complete=1 THEN 1 ELSE 0 END) full_editor_scans
                   FROM telegram_feedback
                   WHERE channel_id=? AND datetime(published_at) >= datetime('now','-7 days')""",
                (int(channel_id),),
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()} if row else {}

    Database._init = init_rc57
    Database.rc57_save_snapshot_batch = save_snapshot_batch
    Database.rc51_feedback_rows = feedback_rows_rc57
    Database.rc57_feedback_rows = feedback_rows_rc57
    Database.rc57_feedback_stats = feedback_stats
    _PATCHED = True
