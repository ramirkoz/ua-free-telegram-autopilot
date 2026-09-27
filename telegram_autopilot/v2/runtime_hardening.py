from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .domain import BlockedBy, Decision, Stage
from .loghub import event
from .media_pipeline import build_media_bundle, media_bundle_complete
from .ready_backlog import ReadyBacklogRuntimeEngine, ReadyBacklogStore
from .storage import _parse_datetime_value, now_iso
from .telegram_ingest_policy import install_ingest_behavior

READY_MEDIA_GRACE_SECONDS = 1800
_READY_MEDIA_CODES = {
    "MEDIA_REQUIRED",
    "MEDIA_INCOMPLETE",
    "MEDIA_DOWNLOAD_FAILED",
    "MEDIA_DOWNLOAD_RETRY",
}


# The production scheduler imports its collector function at module load. Install the
# current V2 composition wrapper before any runtime worker starts; this changes only
# Telegram source composition and leaves bounded scheduling/source health intact.
install_ingest_behavior()


class HardenedReadyStore(ReadyBacklogStore):
    """Current store hardening with source-level text-only publication behavior."""

    def insert_collected(self, **kwargs):
        source_id = int(kwargs.get("source_id") or 0)
        if source_id and self.source_strip_body_links(source_id):
            # The existing visible "Брати ... тільки текст" source setting already
            # strips body links. It now also suppresses source media and adjacent-media
            # composition. The canonical source/footer URL is preserved.
            kwargs["media_json"] = "[]"
            try:
                layout = json.loads(str(kwargs.get("article_layout_json") or "{}"))
            except Exception:
                layout = {}
            if not isinstance(layout, dict):
                layout = {}
            blocks = layout.get("blocks")
            if isinstance(blocks, list):
                layout["blocks"] = [
                    block for block in blocks
                    if not (isinstance(block, dict) and str(block.get("type") or "").casefold() == "media")
                ]
            tg = layout.get("telegram")
            if isinstance(tg, dict):
                tg["media_count"] = 0
                tg["media_group"] = False
                tg["text_only_source"] = True
                tg["stitch_media_suppressed"] = True
            layout["source_text_only"] = True
            kwargs["article_layout_json"] = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
        return super().insert_collected(**kwargs)


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
