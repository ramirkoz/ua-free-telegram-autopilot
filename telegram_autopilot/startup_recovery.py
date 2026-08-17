from __future__ import annotations

from .database import Database


def recover_interrupted_work(db: Database) -> dict[str, int]:
    """Recover transient rows after a previous process exit.

    ``processing`` happens before irreversible external writes, so it is safe to
    return it to the retry queue. Telegraph/Telegram write states are quarantined
    as ``unknown`` because their remote outcome may already have succeeded.
    """
    with db.connect() as con:
        processing = int(con.execute("SELECT COUNT(*) FROM articles WHERE status='processing'").fetchone()[0] or 0)
        external = int(con.execute("SELECT COUNT(*) FROM articles WHERE status IN ('telegraph_writing','telegram_writing')").fetchone()[0] or 0)
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
                WHERE status IN ('telegraph_writing','telegram_writing')"""
            )
    return {"processing_to_retry": processing, "external_to_unknown": external}
