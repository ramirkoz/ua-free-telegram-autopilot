from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .domain import BlockedBy, Decision, Stage
from .loghub import event
from .media_pipeline import build_media_bundle, media_bundle_complete
from .ready_backlog import ReadyBacklogRuntimeEngine, ReadyBacklogStore
from .storage import _parse_datetime_value, now_iso

READY_MEDIA_GRACE_SECONDS = 1800
_READY_MEDIA_CODES = {
    "MEDIA_REQUIRED",
    "MEDIA_INCOMPLETE",
    "MEDIA_DOWNLOAD_FAILED",
    "MEDIA_DOWNLOAD_RETRY",
}


class HardenedReadyStore(ReadyBacklogStore):
    """RC50 store marker; existing Data/schema stay fully compatible."""


class HardenedRuntimeEngine(ReadyBacklogRuntimeEngine):
    """Keep required-media policy fail-closed without leaving immortal READY rows."""

    def _resolve_confirmed_media_misses(self) -> int:
        resolved = int(super()._resolve_confirmed_media_misses() or 0)
        resolved += self._resolve_ready_media_deadlocks()
        return resolved

    def _resolve_ready_media_deadlocks(self) -> int:
        stamp = now_iso()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=READY_MEDIA_GRACE_SECONDS)
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT id,ready_at,discovered_at,last_error_code,next_retry_at
                   FROM articles
                   WHERE stage='READY' AND decision='PUBLISH' AND blocked_by='MEDIA'
                     AND last_error_code IN ('MEDIA_REQUIRED','MEDIA_INCOMPLETE',
                                             'MEDIA_DOWNLOAD_FAILED','MEDIA_DOWNLOAD_RETRY')
                   ORDER BY id ASC LIMIT 250"""
            ).fetchall()

        changed = 0
        for row in rows:
            article_id = int(row["id"])
            article = self.store.get_article(article_id)
            if article is None:
                continue

            bundle = build_media_bundle(article)
            if bundle.count > 0 and media_bundle_complete(bundle):
                recover = getattr(self.store, "_recover_ready_media_blocker", None)
                if callable(recover) and recover(article_id):
                    changed += 1
                continue

            retry_at = _parse_datetime_value(str(row["next_retry_at"] or ""))
            if retry_at is not None and retry_at.astimezone(timezone.utc) > now:
                continue
            born = (
                _parse_datetime_value(str(row["ready_at"] or ""))
                or _parse_datetime_value(str(row["discovered_at"] or ""))
            )
            if born is None or born.astimezone(timezone.utc) > cutoff:
                continue

            code = str(row["last_error_code"] or "MEDIA_REQUIRED")
            reason = (
                "Required-media матеріал знято з READY: після 30-хвилинного recovery window "
                "джерело так і не дало повного валідного медіа для безпечної публікації."
            )
            self.store.update_article(
                article_id,
                stage=str(Stage.ARCHIVED),
                decision=str(Decision.REJECT),
                blocked_by=str(BlockedBy.NONE),
                reject_reason=reason,
                status_detail=reason,
                last_error_code="MEDIA_REQUIRED_EXPIRED",
                last_error_detail=f"{code}: {reason}",
                next_retry_at="",
            )
            with self.store.connect() as con:
                con.execute(
                    """UPDATE jobs
                       SET state='DONE',lease_owner='',lease_until='',error_code='MEDIA_REQUIRED_EXPIRED',
                           error_detail=?,updated_at=?
                       WHERE article_id=? AND state<>'DONE'""",
                    (reason, stamp, article_id),
                )
            event(
                "media",
                "expired permanent READY media blocker",
                level=30,
                article_id=article_id,
                previous_error_code=code,
                media_count=bundle.count,
            )
            changed += 1
        return changed
