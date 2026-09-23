from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .domain import BlockedBy, Decision, Stage
from .guarded_runtime import GuardedRuntimeEngine
from .local_supervisor import LocalOnlyProductionSupervisorService
from .loghub import event
from .media_pipeline import build_media_bundle, media_bundle_complete
from .media_recovery import MediaRecoveryStore
from .storage import _clean_media_json, _media_json_count, _normalize_datetime_value, _parse_datetime_value, now_iso


_RECOVERABLE_READY_MEDIA_CODES = {
    "MEDIA_REQUIRED",
    "MEDIA_INCOMPLETE",
    "MEDIA_DOWNLOAD_FAILED",
    "MEDIA_DOWNLOAD_RETRY",
}


class ReadyBacklogStore(MediaRecoveryStore):
    """Durable RC44 guards for READY rows.

    READY is a publication queue, not an archive. Rows older than the channel TTL
    are retired just like pending process jobs. A fresh source-owned media snapshot
    may also clear an old final-publication media blocker, but only after the normal
    media pipeline still sees a complete publication bundle.
    """

    def run_startup_maintenance(self) -> dict[str, int]:
        stats = dict(super().run_startup_maintenance())
        expired = 0
        for channel in self.list_channels(enabled_only=True):
            expired += self.expire_stale_ready(
                int(channel["id"]),
                int(channel["max_age_hours"] or 0),
            )
        stats["expired_stale_ready"] = expired
        stats["released_nonrequired_media_backlog"] = self._recover_nonrequired_media_backlog()
        return stats

    def _recover_nonrequired_media_backlog(self) -> int:
        """Release legacy required-media blockers after the visible policy becomes preferred/optional.

        The rule is generic and reads persisted channel policy. It never infers a channel from
        its name or ID. Recent rows that were archived only because media was mandatory are
        revived within that channel's normal max-age window.
        """
        stamp = now_iso()
        now = datetime.now(timezone.utc)
        changed = 0
        recover_codes = (
            "MEDIA_REQUIRED", "MEDIA_INCOMPLETE", "MEDIA_DOWNLOAD_FAILED",
            "MEDIA_DOWNLOAD_RETRY", "MEDIA_REQUIRED_SKIPPED", "MEDIA_REQUIRED_EXPIRED",
            "TELEGRAM_MEDIA_REFRESH_REQUIRED",
        )
        placeholders = ",".join("?" for _ in recover_codes)
        with self.connect() as con:
            channels = con.execute(
                """SELECT c.id,c.max_age_hours,COALESCE(p.media_policy,'required') media_policy
                   FROM channels c LEFT JOIN channel_policies p ON p.channel_id=c.id
                   WHERE c.enabled=1"""
            ).fetchall()

        for channel in channels:
            if str(channel["media_policy"] or "required").strip().casefold() == "required":
                continue
            cid = int(channel["id"]); hours = max(1, int(channel["max_age_hours"] or 24))
            cutoff = (now - timedelta(hours=hours)).astimezone().isoformat(timespec="seconds")
            with self.connect() as con:
                cur = con.execute(
                    f"""UPDATE articles SET blocked_by='NONE',last_error_code='',last_error_detail='',next_retry_at=''
                       WHERE channel_id=? AND decision='PUBLISH' AND stage='READY' AND blocked_by='MEDIA'
                         AND last_error_code IN ({placeholders})""",
                    (cid, *recover_codes),
                )
                changed += int(cur.rowcount or 0)

                pending_ids = [int(r[0]) for r in con.execute(
                    f"""SELECT id FROM articles WHERE channel_id=? AND decision='PENDING' AND blocked_by='MEDIA'
                       AND last_error_code IN ({placeholders}) AND discovered_at>=?""",
                    (cid, *recover_codes, cutoff),
                ).fetchall()]
                if pending_ids:
                    qs = ",".join("?" for _ in pending_ids)
                    con.execute(
                        f"UPDATE articles SET blocked_by='NONE',last_error_code='',last_error_detail='',next_retry_at='' WHERE id IN ({qs})",
                        tuple(pending_ids),
                    )
                    cur = con.execute(
                        f"""UPDATE jobs SET state='QUEUED',available_at=?,lease_owner='',lease_until='',
                           error_code='',error_detail='',updated_at=? WHERE article_id IN ({qs}) AND job_type='process'""",
                        (stamp, stamp, *pending_ids),
                    )
                    changed += int(cur.rowcount or 0)

                archived_ids = [int(r[0]) for r in con.execute(
                    f"""SELECT id FROM articles WHERE channel_id=? AND stage='ARCHIVED' AND decision='REJECT'
                       AND last_error_code IN ({placeholders}) AND discovered_at>=?""",
                    (cid, *recover_codes, cutoff),
                ).fetchall()]
                if archived_ids:
                    qs = ",".join("?" for _ in archived_ids)
                    con.execute(
                        f"""UPDATE articles SET stage='COLLECTED',decision='PENDING',blocked_by='NONE',reject_reason='',
                           status_detail='',last_error_code='',last_error_detail='',next_retry_at='',ready_at='',final_text=''
                           WHERE id IN ({qs})""",
                        tuple(archived_ids),
                    )
                    cur = con.execute(
                        f"""UPDATE jobs SET state='QUEUED',available_at=?,lease_owner='',lease_until='',attempts=0,
                           error_code='',error_detail='',updated_at=? WHERE article_id IN ({qs}) AND job_type='process'""",
                        (stamp, stamp, *archived_ids),
                    )
                    changed += int(cur.rowcount or 0)
        if changed:
            event("media", "released backlog after non-required media policy", count=int(changed))
        return int(changed)

    def insert_collected(
        self,
        *,
        channel_id: int,
        source_id: int,
        external_id: str,
        title: str,
        source_url: str,
        raw_text: str,
        content_hash: str = "",
        source_published_at: str = "",
        media_json: str = "[]",
        article_layout_json: str = "{}",
    ) -> int:
        fresh_media = _clean_media_json(media_json)
        article_id = super().insert_collected(
            channel_id=channel_id,
            source_id=source_id,
            external_id=external_id,
            title=title,
            source_url=source_url,
            raw_text=raw_text,
            content_hash=content_hash,
            source_published_at=source_published_at,
            media_json=media_json,
            article_layout_json=article_layout_json,
        )
        # Never clear a media blocker merely because the source was polled again.
        # Recovery requires a genuinely fresh valid media item in this exact ingest.
        if _media_json_count(fresh_media) > 0:
            self._recover_ready_media_blocker(article_id)
        return article_id

    def _recover_ready_media_blocker(self, article_id: int) -> bool:
        row = self.get_article(int(article_id))
        if row is None:
            return False
        if str(row["stage"]) != str(Stage.READY) or str(row["decision"]) != str(Decision.PUBLISH):
            return False
        if str(row["blocked_by"]) != str(BlockedBy.MEDIA):
            return False
        code = str(row["last_error_code"] or "")
        if code not in _RECOVERABLE_READY_MEDIA_CODES:
            return False

        bundle = build_media_bundle(row)
        if bundle.count <= 0 or not media_bundle_complete(bundle):
            return False

        self.update_article(
            int(article_id),
            blocked_by=str(BlockedBy.NONE),
            last_error_code="",
            last_error_detail="",
            next_retry_at="",
            status_detail="",
        )
        event(
            "media",
            "fresh source media unblocked READY publication",
            article_id=int(article_id),
            previous_error_code=code,
            media_count=bundle.count,
        )
        return True

    def expire_stale_ready(self, channel_id: int, max_age_hours: int) -> int:
        hours = int(max_age_hours or 0)
        if hours <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stamp = now_iso()
        reason = f"READY перевищив максимальний вік матеріалу ({hours} год)."

        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                rows = con.execute(
                    """SELECT id,source_published_at,discovered_at
                       FROM articles
                       WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'""",
                    (int(channel_id),),
                ).fetchall()
                ids: list[int] = []
                for row in rows:
                    article_id = int(row["id"])
                    source_raw = str(row["source_published_at"] or "").strip()
                    discovered_raw = str(row["discovered_at"] or "").strip()
                    created = _parse_datetime_value(source_raw) or _parse_datetime_value(discovered_raw)
                    if source_raw:
                        normalized = _normalize_datetime_value(source_raw)
                        if normalized and normalized != source_raw and _parse_datetime_value(normalized) is not None:
                            con.execute(
                                "UPDATE articles SET source_published_at=? WHERE id=?",
                                (normalized, article_id),
                            )
                    if created is not None and created < cutoff:
                        ids.append(article_id)

                if not ids:
                    con.commit()
                    return 0

                ids = list(dict.fromkeys(ids))
                marks = ",".join("?" for _ in ids)
                con.execute(
                    f"""UPDATE articles
                        SET stage=?,decision=?,blocked_by=?,reject_reason=?,status_detail=?,
                            last_error_code='STALE_READY_MAX_AGE',last_error_detail=?,next_retry_at=''
                        WHERE id IN ({marks}) AND stage='READY' AND decision='PUBLISH'""",
                    (
                        str(Stage.ARCHIVED),
                        str(Decision.REJECT),
                        str(BlockedBy.NONE),
                        reason,
                        reason,
                        reason,
                        *ids,
                    ),
                )
                con.execute(
                    f"""UPDATE jobs
                        SET state='DONE',lease_owner='',lease_until='',error_code='STALE_READY_MAX_AGE',
                            error_detail=?,updated_at=?
                        WHERE article_id IN ({marks}) AND state<>'DONE'""",
                    (reason, stamp, *ids),
                )
                con.commit()
            except Exception:
                con.rollback()
                raise

        event(
            "publish",
            "expired stale READY backlog",
            channel_id=int(channel_id),
            count=len(ids),
            max_age_hours=hours,
        )
        return len(ids)


class ReadyBacklogRuntimeEngine(GuardedRuntimeEngine):
    """Expire READY rows on the same one-minute cadence as pending work."""

    def _maybe_expire_stale(self, channel_id: int, max_age_hours: int, state: Any) -> None:
        previous = float(getattr(state, "last_expire_monotonic", 0.0) or 0.0)
        super()._maybe_expire_stale(channel_id, max_age_hours, state)
        current = float(getattr(state, "last_expire_monotonic", 0.0) or 0.0)
        if current == previous:
            return
        expire = getattr(self.store, "expire_stale_ready", None)
        if callable(expire):
            expire(int(channel_id), int(max_age_hours or 0))


class ReadyBacklogSupervisor(LocalOnlyProductionSupervisorService):
    """Expose why READY rows cannot publish, without adding a command channel."""

    def build_snapshot(self) -> dict[str, Any]:
        snapshot = super().build_snapshot()
        stats_all = dict(snapshot.get("channel_stats") or {})
        stamp = now_iso()
        with self.store.connect() as con:
            for channel_id, raw_stats in stats_all.items():
                stats = dict(raw_stats or {})
                rows = con.execute(
                    """SELECT blocked_by,COUNT(*) n
                       FROM articles
                       WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'
                       GROUP BY blocked_by""",
                    (int(channel_id),),
                ).fetchall()
                stats["ready_blockers"] = {
                    str(row["blocked_by"] or "NONE"): int(row["n"] or 0)
                    for row in rows
                }
                stats["ready_publishable"] = int(
                    con.execute(
                        """SELECT COUNT(*) FROM articles
                           WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'
                             AND (blocked_by='NONE' OR (next_retry_at<>'' AND datetime(next_retry_at)<=datetime(?)))""",
                        (int(channel_id), stamp),
                    ).fetchone()[0]
                    or 0
                )
                stats["ready_permanent_blocked"] = int(
                    con.execute(
                        """SELECT COUNT(*) FROM articles
                           WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'
                             AND blocked_by<>'NONE' AND next_retry_at=''""",
                        (int(channel_id),),
                    ).fetchone()[0]
                    or 0
                )
                stats_all[str(channel_id)] = stats
        snapshot["channel_stats"] = stats_all
        supervision = dict(snapshot.get("supervision") or {})
        supervision["ready_backlog_guard"] = True
        snapshot["supervision"] = supervision
        return snapshot
