from __future__ import annotations

import threading

from .domain import BlockedBy, ChannelMode, Decision, Stage
from .loghub import event
from .media_pipeline import build_media_bundle, media_required
from .runtime import RuntimeEngine


class ProductionRuntimeEngine(RuntimeEngine):
    """RC22 runtime hardening for production queues.

    A monitoring item whose strict Telegram ownership filter confirms that there is
    no valid source-owned media must not sit in WAITING/MEDIA forever. Required-media
    channels skip such items deterministically instead of retrying every five minutes.
    """

    def __init__(self, store):
        super().__init__(store)
        self._media_sweeper_stop = threading.Event()
        self._media_sweeper_thread: threading.Thread | None = None

    def start(self) -> None:
        super().start()
        if not self._media_sweeper_thread or not self._media_sweeper_thread.is_alive():
            self._media_sweeper_stop.clear()
            self._media_sweeper_thread = threading.Thread(
                target=self._media_sweeper_loop,
                name="V2-Media-Sweeper",
                daemon=True,
            )
            self._media_sweeper_thread.start()

    def stop(self, timeout: float = 8.0) -> None:
        self._media_sweeper_stop.set()
        super().stop(timeout=timeout)
        thread = self._media_sweeper_thread
        if thread and thread.is_alive():
            thread.join(min(2.0, max(0.2, float(timeout))))

    def _media_sweeper_loop(self) -> None:
        while not self._media_sweeper_stop.wait(15.0):
            try:
                self._resolve_confirmed_media_misses()
            except Exception as exc:
                event("media", "required-media sweeper failed", level=30, detail=str(exc)[:1000])

    def _resolve_confirmed_media_misses(self) -> int:
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT j.id job_id,j.article_id,a.channel_id,a.last_error_code
                   FROM jobs j JOIN articles a ON a.id=j.article_id
                   WHERE j.state='WAITING' AND a.decision='PENDING' AND a.blocked_by='MEDIA'
                     AND a.last_error_code IN ('MEDIA_REQUIRED','TELEGRAM_MEDIA_REFRESH_REQUIRED')
                   ORDER BY j.updated_at ASC LIMIT 250"""
            ).fetchall()

        resolved = 0
        for row in rows:
            channel = self.store.get_channel(int(row["channel_id"]))
            if channel is None or channel.mode != ChannelMode.MONITORING or not media_required(channel):
                continue
            article = self.store.get_article(int(row["article_id"]))
            if article is None or build_media_bundle(article).count:
                continue
            reason = "Моніторинговий матеріал пропущено: після strict ownership/media filter немає валідного медіа точного джерельного поста."
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
