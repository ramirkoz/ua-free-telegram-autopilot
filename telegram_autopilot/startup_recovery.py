from __future__ import annotations

from .ai_router import clear_router_cooldowns
from .database import Database


def _reset_runtime_health_once(db: Database) -> int:
    key = "runtime_health_cleanup_v1"
    if db.get_state(key, "") == "1":
        return 0
    clear_router_cooldowns()
    db.set_state(key, "1")
    return 1


def _requeue_recent_technical_failures_once(db: Database) -> int:
    """Give recent AI/QA infrastructure failures one clean chance after cleanup."""
    key = "runtime_recent_technical_requeue_v1"
    if db.get_state(key, "") == "1":
        return 0
    patterns = (
        "%ai-%", "%ai %", "%router%", "%провайдер%", "%модел%", "%ollama%",
        "%languagetool%", "%qa:%", "%network%", "%http 429%", "%ліміт%",
    )
    with db.connect() as con:
        where = " OR ".join("lower(COALESCE(last_error,'')) LIKE ?" for _ in patterns)
        params = tuple(x.casefold() for x in patterns)
        rows = con.execute(
            f"""SELECT id FROM articles
            WHERE status IN ('retry','error')
              AND datetime(discovered_at) >= datetime('now','-48 hours')
              AND ({where})""", params
        ).fetchall()
        ids = [int(row[0]) for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            con.execute(
                f"""UPDATE articles SET status='new',retry_count=0,next_retry_at=NULL,last_error=NULL,
                processing_started_at=NULL WHERE id IN ({placeholders})""", ids
            )
    db.set_state(key, "1")
    return len(ids)


def recover_interrupted_work(db: Database) -> dict[str, int]:
    """Recover interrupted local work and quarantine uncertain external writes."""
    with db.connect() as con:
        processing = int(con.execute("SELECT COUNT(*) FROM articles WHERE status='processing'").fetchone()[0] or 0)
        external = int(con.execute("SELECT COUNT(*) FROM articles WHERE status='telegram_writing'").fetchone()[0] or 0)
        if processing:
            con.execute(
                """UPDATE articles SET status='retry',next_retry_at=NULL,
                last_error=CASE WHEN COALESCE(last_error,'')='' THEN 'Відновлено після перерваної локальної обробки.' ELSE last_error END
                WHERE status='processing'"""
            )
        if external:
            con.execute(
                """UPDATE articles SET status='unknown',next_retry_at=NULL,
                last_error=CASE WHEN COALESCE(last_error,'')='' THEN 'Попередній процес завершився під час зовнішньої публікації; потрібна перевірка результату.' ELSE last_error END
                WHERE status='telegram_writing'"""
            )
    health_reset = _reset_runtime_health_once(db)
    requeued = _requeue_recent_technical_failures_once(db)
    return {
        "processing_to_retry": processing,
        "external_to_unknown": external,
        "runtime_health_reset": health_reset,
        "recent_technical_requeued": requeued,
    }
