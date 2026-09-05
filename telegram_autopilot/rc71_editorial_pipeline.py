from __future__ import annotations

import base64
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Mapping

LOG = logging.getLogger("telegram_autopilot.rc71")
_INSTALLED = False
_PREV: dict[str, Any] = {}
_CTX = threading.local()

_DEFERRED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _monitoring(channel: Any) -> bool:
    return str(getattr(channel, "channel_mode", "editorial") or "editorial").casefold() == "monitoring"


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None


def _age_hours(article: Any) -> float | None:
    dt = _parse_dt(_v(article, "source_published_at", ""))
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


def _channel_fit_prompt_rc71(policy: Any, article: Any, *, channel_id: int) -> str:
    base = _PREV["channel_fit_prompt"](policy, article, channel_id=channel_id)
    return base + """

RC71 CHANNEL-FIT CONTRACT:
Цей gate відповідає ТІЛЬКИ на питання «цей тип історії належить цьому каналу чи ні?». Він не оцінює загальну цікавість, силу гачка, freshness або media quality.
Шкала fit_score має бути узгоджена з decision:
- 0..39 = явно чужа тема/тип історії або пряме exclusion rule;
- 40..59 = сумнівна/прикордонна відповідність;
- 60..100 = матеріал належить каналу, тому decision ОБОВ'ЯЗКОВО publish.
Не повертай reject разом із fit_score 60 або вище. Якщо історія не проходить політику, знизь fit_score нижче 60 і конкретно назви невідповідність.
""".strip()


def _run_channel_fit_rc71(policy: Any, article: Any, *, channel_id: int):
    result, data = _PREV["run_channel_fit"](policy, article, channel_id=channel_id)
    normalized = dict(data)
    fit = int(normalized.get("fit_score", 0) or 0)
    decision = str(normalized.get("decision") or "").casefold()
    if decision != "publish" and fit >= 60:
        old_reason = " ".join(str(normalized.get("reason") or "").split())
        normalized["decision"] = "publish"
        normalized["reason"] = (
            f"RC71 CHANNEL_FIT_NORMALIZED: fit={fit} означає належність до політики каналу; "
            f"суперечливий reject не застосовано. Попередня причина: {old_reason[:420]}"
        )
        LOG.info(
            "RC71 CHANNEL_FIT_NORMALIZED channel_id=%s article_id=%s fit=%s",
            channel_id, _v(article, "id", "?"), fit,
        )
    return result, normalized


def _value_prompt_rc71(article: Any) -> str:
    base = _PREV["value_prompt"](article)
    from . import rc68_editorial_value as rc68

    channel = rc68._channel(int(_v(article, "channel_id", 0) or 0))
    preferred = max(1, int(getattr(channel, "max_age_hours", 24) or 24)) if channel is not None else 24
    age = _age_hours(article)
    age_text = "невідомий" if age is None else f"приблизно {age:.1f} год."
    return base + f"""

RC71 CONTEXTUAL FRESHNESS:
Вік SOURCE: {age_text}. Налаштований preferred freshness horizon каналу: {preferred} год.
Це М'ЯКИЙ редакційний сигнал, а не hard reject.
- breaking/news швидко втрачає why_now;
- кампанія, кейс, дослідження, аналітика, новий механізм або сильний evergreen-матеріал можуть залишатися цінними довше за цей horizon;
- невідома дата сама по собі НЕ є причиною reject;
- не відхиляй матеріал лише через те, що він старший за {preferred} год. Оціни, чи зберігся реальний reader payoff і why_now для цього ТИПУ історії.
""".strip()


def _recover_recent_legacy_rejects(db: Any, channel_id: int) -> int:
    marker = f"rc71_editorial_recovery_v1:{int(channel_id)}"
    try:
        if db.get_state(marker, "0") == "1":
            return 0
    except Exception:
        pass
    patterns = (
        "RC61 FRESHNESS%",
        "Матеріал старіший%",
        "RC66 READY expired%",
        "Немає придатного фото/відео%",
        "%CHANNEL_POLICY_REJECT%",
        "%RC68 EDITORIAL_VALUE_REJECT%",
    )
    with db.connect() as con:
        rows = con.execute(
            """SELECT id FROM articles
               WHERE channel_id=? AND status='rejected'
                 AND datetime(discovered_at)>=datetime('now','-72 hours')
                 AND (reject_reason LIKE ? OR reject_reason LIKE ? OR reject_reason LIKE ? OR
                      reject_reason LIKE ? OR reject_reason LIKE ? OR reject_reason LIKE ?)
               ORDER BY id DESC LIMIT 240""",
            (int(channel_id), *patterns),
        ).fetchall()
        ids = [int(row[0]) for row in rows]
        for aid in ids:
            con.execute(
                """UPDATE articles SET status='new',reject_reason=NULL,last_error=NULL,
                       processing_started_at=NULL,retry_count=0,next_retry_at=NULL,
                       editorial_value_score=NULL,editorial_value_json='',editorial_value_reason='',editorial_value_checked_at=NULL
                   WHERE id=?""",
                (aid,),
            )
    try:
        db.set_state(marker, "1")
    except Exception:
        pass
    return len(ids)


def _contextual_pending(db: Any, channel_id: int, limit: int = 20):
    rescued = _recover_recent_legacy_rejects(db, int(channel_id))
    if rescued:
        LOG.info("RC71 requeued recent editorial rejects channel_id=%s rescued=%s", channel_id, rescued)
    scan_limit = max(80, min(600, int(limit) * 10))
    with db.connect() as con:
        rows = con.execute(
            """SELECT a.*,s.name AS source_name,s.priority AS source_priority,s.kind AS source_kind,s.url AS source_url,
                      c.max_age_hours AS channel_max_age
               FROM articles a
               JOIN sources s ON s.id=a.source_id
               JOIN channels c ON c.id=a.channel_id
               WHERE a.channel_id=? AND a.cluster_parent_id IS NULL AND (
                   a.status='new' OR (
                       a.status='retry' AND (
                           a.next_retry_at IS NULL OR a.next_retry_at='' OR datetime(a.next_retry_at)<=datetime('now')
                       )
                   )
               )
               ORDER BY CASE WHEN a.status='new' THEN 0 ELSE 1 END,
                        s.priority DESC,
                        CASE WHEN a.status='new' THEN a.id END DESC,
                        CASE WHEN a.status='retry' THEN datetime(COALESCE(NULLIF(a.next_retry_at,''),a.discovered_at)) END ASC,
                        a.id DESC
               LIMIT ?""",
            (int(channel_id), scan_limit),
        ).fetchall()
    return list(rows)[: max(1, int(limit))]


def _has_publishable_media(value: Any) -> bool:
    try:
        return value.telegram_hero is not None or value.telegram_direct_video is not None
    except Exception:
        return False


def _deferred_media():
    from .media_pipeline import PreparedArticleMedia, PreparedMedia

    item = PreparedMedia(
        index=-7100,
        kind="image",
        url="https://rc71.invalid/deferred-media.png",
        caption="RC71 deferred media gate",
        alt="RC71 deferred media gate",
        position=0.0,
        featured=True,
        mime_type="image/png",
        width=1,
        height=1,
        digest="rc71-deferred",
        data=_DEFERRED_PNG,
        context="internal deferred-media sentinel",
        classification="photo",
        relevance_score=100.0,
    )
    return PreparedArticleMedia(featured=item, body=[])


def _context_article() -> tuple[Any | None, Any | None, Any | None]:
    service = getattr(_CTX, "service", None)
    channel = getattr(_CTX, "channel", None)
    article_id = getattr(_CTX, "article_id", None)
    if service is None or article_id is None:
        return service, channel, None
    try:
        return service, channel, service.db.get_article(int(article_id))
    except Exception:
        return service, channel, None


def _prepare_media_rc71(layout_json: str, media_urls: list[str], *, title: str = "", article_text: str = "", marketing_context: bool = False):
    current = _PREV["prepare_media"](
        layout_json, media_urls, title=title, article_text=article_text, marketing_context=marketing_context
    )
    if _has_publishable_media(current):
        return current

    service, channel, row = _context_article()
    if service is not None and row is not None:
        try:
            from .rc66_clusters import cluster_members
            current_id = int(_v(row, "id", 0) or 0)
            for member in cluster_members(service.db, row):
                if int(_v(member, "id", 0) or 0) == current_id:
                    continue
                candidate = _PREV["prepare_media"](
                    service.db.article_layout_json(member),
                    service.db.media_urls(member),
                    title=str(_v(member, "title", "") or title),
                    article_text=str(_v(member, "raw_text", "") or article_text),
                    marketing_context=marketing_context,
                )
                if _has_publishable_media(candidate):
                    try:
                        service._audit(
                            "rc71_media", "cluster_fallback",
                            f"media borrowed from cluster member #{int(_v(member,'id',0) or 0)}",
                            channel_id=int(channel.id), article_id=current_id,
                        )
                    except Exception:
                        pass
                    return candidate
        except Exception as exc:
            LOG.debug("RC71 cluster media fallback failed: %s", exc)

    if channel is not None and not _monitoring(channel):
        try:
            from . import rc66_editorial_queue as rc66
            if bool(getattr(rc66._CONTEXT, "preparing", False)):
                if service is not None and row is not None:
                    try:
                        service._audit(
                            "rc71_media", "deferred",
                            "no Telegram-ready media yet; editorial evaluation continues before final media gate",
                            channel_id=int(channel.id), article_id=int(_v(row, "id", 0) or 0),
                        )
                    except Exception:
                        pass
                return _deferred_media()
        except Exception:
            pass
    return current


def _with_context(service: Any, channel: Any, article_id: int | None, fn, *args, **kwargs):
    old = (
        getattr(_CTX, "service", None),
        getattr(_CTX, "channel", None),
        getattr(_CTX, "article_id", None),
    )
    _CTX.service, _CTX.channel, _CTX.article_id = service, channel, article_id
    try:
        return fn(*args, **kwargs)
    finally:
        _CTX.service, _CTX.channel, _CTX.article_id = old


def _core_process_rc71(service: Any, channel: Any):
    try:
        from . import rc67_nonblocking_runtime as rc67
        article_id = getattr(rc67._TARGET, "article_id", None)
    except Exception:
        article_id = None
    return _with_context(service, channel, article_id, _PREV["core_process"], service, channel)


def _publish_one_rc71(service: Any, channel: Any, row: Any) -> bool:
    return bool(
        _with_context(
            service, channel, int(_v(row, "id", 0) or 0), _PREV["publish_one"], service, channel, row
        )
    )


def _never_hard_stale(*_args: Any, **_kwargs: Any) -> bool:
    return False


def install_rc71_editorial_pipeline() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import media_pipeline
    from . import rc66_editorial_queue as rc66
    from . import rc67_nonblocking_runtime as rc67
    from . import rc68_editorial_value as rc68
    from . import service as svc

    _PREV.update(
        channel_fit_prompt=rc68._channel_fit_prompt,
        run_channel_fit=rc68._run_channel_fit,
        value_prompt=rc68._value_prompt,
        pending=rc68._PREV.get("pending"),
        service_is_too_old=svc.AutopilotService._is_too_old,
        ready_too_old=rc66._too_old,
        prepare_media=media_pipeline.prepare_article_media,
        core_process=rc67._PREV.get("core_process"),
        publish_one=rc66._publish_one,
    )

    rc68._channel_fit_prompt = _channel_fit_prompt_rc71
    rc68._run_channel_fit = _run_channel_fit_rc71
    rc68._value_prompt = _value_prompt_rc71
    rc68._PREV["pending"] = _contextual_pending
    rc68._GATE_VERSION = 3

    svc.AutopilotService._is_too_old = _never_hard_stale
    rc66._too_old = _never_hard_stale

    media_pipeline.prepare_article_media = _prepare_media_rc71
    svc.prepare_article_media = _prepare_media_rc71
    if _PREV["core_process"] is not None:
        rc67._PREV["core_process"] = _core_process_rc71
    rc66._publish_one = _publish_one_rc71

    LOG.info(
        "RC71 installed: universal editorial gate order, consistent channel-fit contract, contextual freshness, "
        "cluster media fallback and deferred media rejection; monitoring editorial bypass remains intact"
    )
    _INSTALLED = True
