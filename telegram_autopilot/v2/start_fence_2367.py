"""Retire unsent pre-start work before workers and collectors start."""
from .freshness_fence_241 import _aware

def retire_prestart_unattempted_2367(store, started_at: str) -> int:
    started = _aware(started_at)
    if started is None:
        raise ValueError("RUNTIME_START_UNVERIFIED")
    retired = 0
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute("""SELECT id,source_published_at FROM articles
            WHERE stage IN ('COLLECTED','EXTRACTED','SELECTED','WRITTEN','QA_PASSED','READY')
            AND decision IN ('PENDING','PUBLISH')
            AND COALESCE(published_at,'')='' AND COALESCE(telegram_message_id,'')=''
            AND NOT EXISTS(SELECT 1 FROM publication_delivery_journal d WHERE d.article_id=articles.id)
            AND NOT EXISTS(SELECT 1 FROM delivery_receipt_archive d WHERE d.article_id=articles.id)
            AND NOT EXISTS(SELECT 1 FROM editorial_actions e WHERE e.article_id=articles.id AND e.action IN ('publish_attempt','publish_now'))
            AND COALESCE(article_layout_json,'') NOT LIKE '%telegram_delivery%'""").fetchall()
        for row in rows:
            published = _aware(str(row['source_published_at'] or ''))
            if published is not None and published >= started:
                continue
            reason = 'SOURCE_FRESHNESS:' + ('SOURCE_PREDATES_RUNTIME_START' if published is not None else 'SOURCE_DATE_UNVERIFIED')
            con.execute("""UPDATE articles SET stage='ARCHIVED',decision='REJECT',blocked_by='QUALITY',
                reject_reason=?,status_detail=?,last_error_code='EDITORIAL_HARD_REJECT',last_error_detail=?,next_retry_at='' WHERE id=?""",
                (reason,reason,reason,row['id']))
            con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',error_code='',error_detail='',updated_at=? WHERE article_id=?",(started_at,row['id']))
            retired += 1
    return retired
