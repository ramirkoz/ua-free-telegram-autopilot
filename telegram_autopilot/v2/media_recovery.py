from __future__ import annotations

from datetime import datetime, timezone

from .domain import BlockedBy, ChannelMode, Decision, Stage
from .hardened_storage import HardenedV2Store
from .loghub import event
from .media_pipeline import build_media_bundle, media_required
from .production_runtime import ProductionRuntimeEngine


MEDIA_REQUIRED_GRACE_SECONDS = 600


class MediaRecoveryStore(HardenedV2Store):
    """Recover required-media monitoring rows when a later source poll finds media.

    RC27 could archive a monitoring item as ``MEDIA_REQUIRED_SKIPPED`` only seconds
    after the first incomplete Telegram snapshot.  If the next poll later revealed
    the real photo/album, the article stayed archived forever because DONE jobs were
    never resurrected.  A fresh source-owned media snapshot is authoritative and
    revives that exact article/job without changing the channel's required-media
    policy.
    """

    def insert_collected(self, **kwargs) -> int:
        article_id = super().insert_collected(**kwargs)
        row = self.get_article(article_id)
        if row is None or str(row["last_error_code"] or "") != "MEDIA_REQUIRED_SKIPPED":
            return article_id
        if build_media_bundle(row).count <= 0:
            return article_id

        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.connect() as con:
            con.execute(
                """UPDATE articles
                   SET stage='COLLECTED',decision='PENDING',reject_reason='',blocked_by='NONE',
                       ready_at='',final_text='',last_error_code='',last_error_detail='',next_retry_at=''
                   WHERE id=?""",
                (int(article_id),),
            )
            con.execute(
                """UPDATE jobs
                   SET state='QUEUED',available_at=?,lease_owner='',lease_until='',attempts=0,
                       error_code='',error_detail='',updated_at=?
                   WHERE article_id=? AND job_type='process'""",
                (stamp, stamp, int(article_id)),
            )
        event("media", "revived archived required-media item after source refresh", article_id=int(article_id))
        return article_id


class MediaRecoveryRuntimeEngine(ProductionRuntimeEngine):
    """Give Telegram/media refresh a real grace window before permanent skip."""

    def _resolve_confirmed_media_misses(self) -> int:
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT j.id job_id,j.article_id,a.channel_id,a.last_error_code,a.discovered_at
                   FROM jobs j JOIN articles a ON a.id=j.article_id
                   WHERE j.state='WAITING' AND a.decision='PENDING' AND a.blocked_by='MEDIA'
                     AND a.last_error_code IN ('MEDIA_REQUIRED','TELEGRAM_MEDIA_REFRESH_REQUIRED','TELEGRAM_VIDEO_PENDING')
                   ORDER BY j.updated_at ASC LIMIT 250"""
            ).fetchall()

        resolved = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            channel = self.store.get_channel(int(row["channel_id"]))
            if channel is None or channel.mode != ChannelMode.MONITORING or not media_required(channel):
                continue
            article = self.store.get_article(int(row["article_id"]))
            if article is None or build_media_bundle(article).count:
                continue
            try:
                discovered = datetime.fromisoformat(str(row["discovered_at"] or "").replace("Z", "+00:00"))
                if discovered.tzinfo is None:
                    discovered = discovered.replace(tzinfo=timezone.utc)
                age_seconds = max(0.0, (now - discovered.astimezone(timezone.utc)).total_seconds())
            except Exception:
                age_seconds = 0.0
            if age_seconds < MEDIA_REQUIRED_GRACE_SECONDS:
                continue

            reason = (
                "Моніторинговий матеріал пропущено: після 10-хвилинного media grace "
                "і повторних source refresh немає валідного медіа точного джерельного поста."
            )
            self.store.update_article(
                int(row["article_id"]),
                stage=str(Stage.ARCHIVED),
                decision=str(Decision.REJECT),
                blocked_by=str(BlockedBy.NONE),
                reject_reason=reason,
                last_error_code="MEDIA_REQUIRED_SKIPPED",
                last_error_detail=reason,
                next_retry_at="",
            )
            self.store.finish_job(int(row["job_id"]))
            resolved += 1
        if resolved:
            event("media", "resolved permanent required-media backlog", count=resolved)
        return resolved
