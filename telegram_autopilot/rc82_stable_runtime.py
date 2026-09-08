from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from . import ai_router

LOG = logging.getLogger("telegram_autopilot.rc82")
_INSTALLED = False
_ORIGINAL_UPDATE_ARTICLE = None
_ORIGINAL_SCHEDULE_RETRY = None
_ORIGINAL_PREPARE_ONE = None
_ORIGINAL_PUBLISH_ONE = None
_LAST_WAKE: dict[int, float] = {}

_OUTAGE_MARKERS = (
    "немає доступного ai-провайдера",
    "усі налаштовані провайдери",
    "усі доступні ai-моделі",
    "network request failed",
    "connection error",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
    "http 503",
    "http 502",
    "http 504",
    "temporarily unavailable",
    "server busy",
    "overload",
    "quota",
    "досягнуто ліміт",
    "rate limit",
    "429",
    "ollama не завершила",
    "local ai",
    "codex не виконав запит",
    "model does not exist",
    "model_not_found",
    "model is not supported",
)


def _clean(value: Any, limit: int = 2000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _provider_outage_text(message: str) -> bool:
    low = _clean(message, 4000).casefold()
    # A candidate rejected by factual/language QA is content-specific, not a
    # provider outage. Let the ordinary bounded retry logic handle that case.
    if any(token in low for token in ("post-ai qa", "fact guard", "language qa", "редакційний qa")) and not any(
        marker in low for marker in ("quota", "429", "network request failed", "timeout", "http 503", "ollama")
    ):
        return False
    return any(marker in low for marker in _OUTAGE_MARKERS)


def _technical_reject(reason: str) -> bool:
    low = _clean(reason, 3000).casefold()
    return bool(
        "selector_unavailable" in low
        or "редакційний selector не дав валідного рішення" in low
        or ("monitoring" in low and "gate unavailable" in low)
    )


def _next_retry(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(seconds)))).isoformat(timespec="seconds")


def _update_article_rc82(self: Any, article_id: int, **fields: Any) -> None:
    # Fundamental contract: a technical selector outage is never an editorial
    # rejection. Keep the article recoverable and visibly marked WAITING_AI.
    if str(fields.get("status") or "") == "rejected":
        reason = str(fields.get("reject_reason") or "")
        if _technical_reject(reason):
            fields = dict(fields)
            fields["status"] = "retry"
            fields["reject_reason"] = None
            fields["last_error"] = ("WAITING_AI: " + _clean(reason, 1800))[:2000]
            fields["retry_count"] = 0
            fields["next_retry_at"] = _next_retry(120)
            fields["processing_started_at"] = None
    return _ORIGINAL_UPDATE_ARTICLE(self, int(article_id), **fields)


def _schedule_retry_rc82(self: Any, article_id: int, error: str, *, max_attempts: int = 5) -> str:
    if not _provider_outage_text(error):
        return _ORIGINAL_SCHEDULE_RETRY(self, int(article_id), error, max_attempts=max_attempts)

    # Provider outages are external system state, not an article defect. They
    # may wait all night but must never be converted to terminal ERROR solely
    # because several providers were unavailable in a row.
    with self.connect() as con:
        row = con.execute("SELECT retry_count FROM articles WHERE id=?", (int(article_id),)).fetchone()
        if not row:
            return "error"
        attempt = int(row[0] or 0) + 1
        delay = 120 if attempt <= 1 else 300 if attempt <= 3 else 900
        con.execute(
            """UPDATE articles
               SET status='retry',retry_count=?,next_retry_at=?,processing_started_at=NULL,
                   last_error=?,reject_reason=NULL
               WHERE id=?""",
            (
                attempt,
                _next_retry(delay),
                ("WAITING_AI: " + _clean(error, 1800))[:2000],
                int(article_id),
            ),
        )
    return "retry"


def _healthy_provider_available() -> bool:
    try:
        cfg = ai_router.load_secrets()
        slots = ai_router._runtime_model_slots(cfg)
        return any(ai_router._configured(slot, cfg) and not ai_router._slot_on_cooldown(slot) for slot in slots)
    except Exception:
        # A health probe failure itself must not stop the old proven router.
        return True


def _wake_waiting_ai(db: Any, channel_id: int, *, limit: int = 6) -> int:
    now = time.monotonic()
    if now - _LAST_WAKE.get(int(channel_id), 0.0) < 30.0:
        return 0
    _LAST_WAKE[int(channel_id)] = now
    with db.connect() as con:
        rows = con.execute(
            """SELECT id FROM articles
               WHERE channel_id=? AND status='retry' AND last_error LIKE 'WAITING_AI:%'
               ORDER BY id DESC LIMIT ?""",
            (int(channel_id), max(1, int(limit))),
        ).fetchall()
        ids = [int(row[0]) for row in rows]
        for article_id in ids:
            con.execute(
                "UPDATE articles SET next_retry_at=datetime('now'),processing_started_at=NULL WHERE id=?",
                (article_id,),
            )
    return len(ids)


def _prepare_one_rc82(service: Any, channel: Any) -> bool:
    if not _healthy_provider_available():
        # Leave fresh material NEW. Collection continues; editorial AI resumes
        # automatically when a route becomes healthy.
        return False
    awakened = _wake_waiting_ai(service.db, int(channel.id))
    if awakened:
        service._audit(
            "rc82_ai_recovery",
            "wake",
            f"healthy AI available; woke {awakened} WAITING_AI rows (fresh NEW rows still have priority)",
            channel_id=int(channel.id),
        )
    return _ORIGINAL_PREPARE_ONE(service, channel)


def _valid_source_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _source_urls(db: Any, row: Any) -> list[str]:
    from .rc66_clusters import source_urls

    return [url for url in source_urls(db, row) if _valid_source_url(url)]


def _publish_one_rc82(service: Any, channel: Any, row: Any) -> bool:
    aid = int(getattr(row, "id", 0) or 0)
    if not aid:
        try:
            aid = int(row["id"])
        except Exception:
            return False
    fresh = service.db.get_article(aid)
    if fresh is None:
        return False
    urls = _source_urls(service.db, fresh)
    if not urls:
        # A URL occurring inside the article body (registration sheet, phone,
        # practical link) is not source attribution. The collected article/cluster
        # itself must have a traceable source URL before Telegram is allowed.
        _ORIGINAL_UPDATE_ARTICLE(
            service.db,
            aid,
            status="error",
            reject_reason=None,
            last_error="SOURCE_MISSING: публікацію заблоковано — немає валідного URL джерела матеріалу.",
            next_retry_at=None,
            processing_started_at=None,
        )
        service._audit(
            "rc82_source_gate",
            "blocked",
            "No canonical source URL; Telegram publish forbidden",
            channel_id=int(channel.id),
            article_id=aid,
        )
        return False
    return _ORIGINAL_PUBLISH_ONE(service, channel, row)


def _clear_legacy_cooldowns_once(db: Any) -> None:
    key = "rc82_legacy_ai_state_reset"
    try:
        if db.get_state(key, ""):
            return
        ai_router.clear_router_cooldowns()
        db.set_state(key, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        LOG.info("RC82 cleared legacy RC81 cooldown/model state once")
    except Exception:
        LOG.warning("RC82 could not clear legacy AI cooldowns", exc_info=True)


def repair_rc82_startup(db: Any, *, limit: int = 40) -> tuple[int, int]:
    """Recover only technical RC80/81 failures; never revive true editorial rejects."""
    _clear_legacy_cooldowns_once(db)
    recovered_rejects = 0
    recovered_waiters = 0
    stamp = datetime.now(timezone.utc)
    with db.connect() as con:
        rows = con.execute(
            """SELECT id,reject_reason FROM articles
               WHERE status='rejected' AND datetime(discovered_at)>=datetime('now','-72 hours')
               ORDER BY id DESC LIMIT 300"""
        ).fetchall()
        for index, row in enumerate(rows):
            if recovered_rejects >= max(1, int(limit // 2)):
                break
            reason = str(row[1] or "")
            if not _technical_reject(reason):
                continue
            next_retry = (stamp + timedelta(seconds=30 + recovered_rejects * 15)).isoformat(timespec="seconds")
            con.execute(
                """UPDATE articles SET status='retry',reject_reason=NULL,last_error=?,retry_count=0,
                   next_retry_at=?,processing_started_at=NULL WHERE id=?""",
                (("WAITING_AI: recovered technical selector outage: " + _clean(reason, 1300))[:2000], next_retry, int(row[0])),
            )
            recovered_rejects += 1

        rows = con.execute(
            """SELECT id FROM articles
               WHERE status IN ('retry','error') AND last_error LIKE 'WAITING_AI:%'
                 AND datetime(discovered_at)>=datetime('now','-72 hours')
               ORDER BY id DESC LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        for index, row in enumerate(rows):
            next_retry = (stamp + timedelta(seconds=60 + index * 20)).isoformat(timespec="seconds")
            con.execute(
                """UPDATE articles SET status='retry',retry_count=0,next_retry_at=?,processing_started_at=NULL,
                   reject_reason=NULL WHERE id=?""",
                (next_retry, int(row[0])),
            )
            recovered_waiters += 1
    LOG.info("RC82 startup repair technical_rejects=%s waiting_ai=%s", recovered_rejects, recovered_waiters)
    return recovered_rejects, recovered_waiters


def install_rc82_stable_runtime() -> None:
    global _INSTALLED, _ORIGINAL_UPDATE_ARTICLE, _ORIGINAL_SCHEDULE_RETRY, _ORIGINAL_PREPARE_ONE, _ORIGINAL_PUBLISH_ONE
    if _INSTALLED:
        return

    from .database import Database
    from . import rc66_editorial_queue as rc66
    from . import rc67_nonblocking_runtime as rc67

    _ORIGINAL_UPDATE_ARTICLE = Database.update_article
    _ORIGINAL_SCHEDULE_RETRY = Database.schedule_retry
    _ORIGINAL_PREPARE_ONE = rc67._prepare_one
    _ORIGINAL_PUBLISH_ONE = rc66._publish_one

    Database.update_article = _update_article_rc82
    Database.schedule_retry = _schedule_retry_rc82
    rc67._prepare_one = _prepare_one_rc82
    rc66._publish_one = _publish_one_rc82

    LOG.info(
        "RC82 installed: RC79/80 editorial runtime preserved; technical rejects defer, provider outages never terminal, healthy AI wakes waiters, source URL required before Telegram"
    )
    _INSTALLED = True
