from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .database import Database


_INSTALLED = False
_RETRY_DELAYS_SECONDS = (120, 300, 900, 1800)
_MAX_RETRY_ATTEMPTS = 5


def install_queue_hotfix() -> None:
    """Install the RC9 queue-starvation/backoff compatibility fix.

    RC8/early-RC9 Data can contain many old ``retry`` rows. The original RC9
    scheduler sorted ``new`` and ``retry`` together by ascending id, allowing
    historical failures to occupy the whole pending window forever. This fix:

    * adds retry metadata to existing Data additively;
    * gives fresh ``new`` rows absolute priority;
    * applies bounded retry backoff to failed rows;
    * moves a row to ``error`` after five failed attempts.

    The patch is deliberately installed at runtime so the RC9 database format is
    preserved and no destructive migration or Data reset is required.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original_init = Database._init
    original_update_article = Database.update_article

    def patched_init(self: Database) -> None:
        original_init(self)
        with self.connect() as con:
            self._ensure_column(con, "articles", "retry_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(con, "articles", "next_retry_at", "TEXT")

    def pending_articles(self: Database, channel_id: int, limit: int = 20):
        with self.connect() as con:
            return con.execute(
                """SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id
                WHERE a.channel_id=? AND (
                    a.status='new' OR (
                        a.status='retry' AND (
                            a.next_retry_at IS NULL OR a.next_retry_at='' OR datetime(a.next_retry_at) <= datetime('now')
                        )
                    )
                )
                ORDER BY CASE WHEN a.status='new' THEN 0 ELSE 1 END, a.id ASC
                LIMIT ?""",
                (channel_id, limit),
            ).fetchall()

    def schedule_retry(self: Database, article_id: int, error: str, *, max_attempts: int = _MAX_RETRY_ATTEMPTS) -> str:
        with self.connect() as con:
            row = con.execute("SELECT retry_count FROM articles WHERE id=?", (article_id,)).fetchone()
            if not row:
                return "error"
            attempt = int(row[0] or 0) + 1
            if attempt >= max(1, int(max_attempts)):
                con.execute(
                    "UPDATE articles SET status='error',retry_count=?,next_retry_at=NULL,last_error=? WHERE id=?",
                    (attempt, str(error)[:2000], article_id),
                )
                return "error"
            delay = _RETRY_DELAYS_SECONDS[min(attempt - 1, len(_RETRY_DELAYS_SECONDS) - 1)]
            next_retry = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
            con.execute(
                "UPDATE articles SET status='retry',retry_count=?,next_retry_at=?,last_error=? WHERE id=?",
                (attempt, next_retry, str(error)[:2000], article_id),
            )
            return "retry"

    def patched_update_article(self: Database, article_id: int, **fields: object) -> None:
        status = str(fields.get("status") or "")
        last_error = fields.get("last_error")

        # Existing service.py reports retryable failures as status=retry plus an
        # error string. Convert exactly those writes into bounded backoff. Successful
        # intermediate retry states (AI result saved / Telegraph page saved) do not
        # carry last_error and therefore keep their original resume semantics.
        if status == "retry" and last_error not in (None, ""):
            schedule_retry(self, article_id, str(last_error))
            return

        original_update_article(self, article_id, **fields)
        if status == "published":
            with self.connect() as con:
                con.execute(
                    "UPDATE articles SET retry_count=0,next_retry_at=NULL,last_error=NULL WHERE id=?",
                    (article_id,),
                )
        elif status in {"error", "unknown", "duplicate", "rejected"}:
            with self.connect() as con:
                con.execute("UPDATE articles SET next_retry_at=NULL WHERE id=?", (article_id,))

    Database._init = patched_init  # type: ignore[assignment]
    Database.pending_articles = pending_articles  # type: ignore[assignment]
    Database.schedule_retry = schedule_retry  # type: ignore[attr-defined]
    Database.update_article = patched_update_article  # type: ignore[assignment]
    _INSTALLED = True
