from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

from .rc66_clusters import composite_row, prepare_clusters, source_urls
from .rc66_tags import StoryTags, related, row_tags, v

LOG = logging.getLogger("telegram_autopilot.rc66")
_INSTALLED = False
_CONTEXT = threading.local()
_PREV: dict[str, Any] = {}
POLL_IMMEDIATE_SECONDS = 15


def _validate_hhmm(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text) else fallback


def publication_window_open(channel: Any, *, now: datetime | None = None) -> bool:
    if bool(getattr(channel, "publish_24h", False)):
        return True
    current = now or datetime.now().astimezone()
    start = _validate_hhmm(getattr(channel, "publish_start", "07:00"), "07:00")
    end = _validate_hhmm(getattr(channel, "publish_end", "00:00"), "00:00")
    sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
    a, b, cur = sh * 60 + sm, eh * 60 + em, current.hour * 60 + current.minute
    if a == b:
        return True
    return a <= cur < b if a < b else cur >= a or cur < b


def _gap_ok(service: Any, channel: Any) -> bool:
    if bool(getattr(_CONTEXT, "preparing", False)) or bool(getattr(channel, "publish_immediately", False)):
        return True
    gap = max(0, int(getattr(channel, "min_publish_interval_minutes", 0) or 0))
    if not gap:
        return True
    last = service.db.last_published_at(int(channel.id))
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt.astimezone(timezone.utc) >= timedelta(minutes=gap)
    except Exception:
        return True


def _run_channel(service: Any, channel: Any, *, force: bool) -> None:
    now = time.monotonic()
    seconds = POLL_IMMEDIATE_SECONDS if bool(getattr(channel, "poll_immediate", False)) else max(1, int(channel.poll_interval_minutes or 1)) * 60
    if force or now - service._last_collect.get(int(channel.id), 0) >= seconds:
        service._collect(channel, force=force)
        service._last_collect[int(channel.id)] = now
    service._process(channel)


def _pending(db: Any, cid: int, limit: int = 20):
    out = []
    for row in _PREV["pending"](db, int(cid), limit):
        if str(v(row, "status", "") or "") == "clustered" or int(v(row, "cluster_parent_id", 0) or 0):
            continue
        out.append(composite_row(db, row))
    return out


def _mark_ready(db: Any, article_id: int, fields: dict[str, Any]) -> None:
    safe = dict(fields)
    for key in ("published_at", "telegram_message_id", "telegram_media_count"):
        safe.pop(key, None)
    safe.update(status="ready", retry_count=0, next_retry_at=None, last_error=None, reject_reason=None)
    _PREV["update_article"](db, article_id, **safe)
    with db.connect() as con:
        con.execute("UPDATE articles SET ready_at=? WHERE id=?", (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), article_id))


def _update_article(db: Any, article_id: int, **fields: Any) -> None:
    if bool(getattr(_CONTEXT, "preparing", False)) and str(fields.get("status") or "") == "published":
        _mark_ready(db, int(article_id), fields); return
    _PREV["update_article"](db, int(article_id), **fields)


def _fake_result(media_count: int = 1):
    from .telegram import TelegramResult
    return TelegramResult("rc66-ready", ("rc66-ready",), media_count)


def _send_photo(*args: Any, **kwargs: Any):
    return _fake_result() if bool(getattr(_CONTEXT, "preparing", False)) else _PREV["send_photo"](*args, **kwargs)


def _send_video(*args: Any, **kwargs: Any):
    return _fake_result() if bool(getattr(_CONTEXT, "preparing", False)) else _PREV["send_video"](*args, **kwargs)


def _audit(service: Any, stage: str, outcome: str, detail: str = "", **refs: Any) -> None:
    if bool(getattr(_CONTEXT, "preparing", False)) and stage == "telegram":
        if outcome == "writing":
            return _PREV["audit"](service, "rc66_ready", "preparing", detail, **refs)
        if outcome == "published":
            return _PREV["audit"](service, "rc66_ready", "ready", detail, **refs)
    return _PREV["audit"](service, stage, outcome, detail, **refs)


def _emit(service: Any, kind: str, text: str) -> None:
    if bool(getattr(_CONTEXT, "preparing", False)) and kind == "publish":
        return _PREV["emit"](service, "ready", str(text).replace("опубліковано", "підготовлено у READY-пул"))
    return _PREV["emit"](service, kind, text)


def structural_issue(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "порожній текст"
    if value.count("(") != value.count(")") or value.count("[") != value.count("]"):
        return "незакрита дужка"
    if value.count("«") != value.count("»"):
        return "незакриті лапки"
    low = value.casefold().rstrip()
    if re.search(r"(?:\b(?:і|й|але|або|бо|що|який|яка|яке|які|щоб|тому що|через|після|до|для|з|із|на|у|в|та)\s*)$", low):
        return "думка обірвана на службовому слові"
    if value.endswith((":", ";", ",", "—", "-", "/")):
        return "речення обірване на пунктуації"
    if value[-1] not in ".!?…)]»\"'":
        tail = value.rsplit("\n", 1)[-1].strip()
        final = re.split(r"(?<=[.!?…])\s+", tail)[-1].strip()
        if len(final.split()) >= 4:
            return "останнє речення не завершене"
    return ""


def _final_edit(channel: Any, article: Any, decision: Any, *, hard_limit: int):
    from . import production_pipeline as prod
    result = _PREV["final_edit"](channel, article, decision, hard_limit=hard_limit)
    if getattr(result, "decision", "") == "publish":
        issue = structural_issue(str(getattr(result, "telegram_teaser", "") or ""))
        if issue:
            raise prod.ProductionPipelineError(f"RC66 FINAL STRUCTURE BLOCK: {issue}")
    return result


def _selector(policy: Any, article: Any, *, channel_id: int = 0):
    result, data = _PREV["selector"](policy, article, channel_id=channel_id)
    data = dict(data)
    if str(data.get("decision") or "") == "publish":
        return result, data
    reason = " ".join(str(data.get("reason") or "").split())
    low = reason.casefold()
    hard = ("off-topic", "off topic", "не по тем", "поза темат", "немає фактич", "без фактич", "sponsored", "advertorial", "rumor", "чутк", "buying guide", "not news", "не новин", "не стосується", "не релевант")
    if any(x in low for x in hard):
        return result, data
    fit = int(data.get("fit_score", 0) or 0)
    marketing = False
    try:
        from . import rc62_editorial_control as rc62
        marketing = bool(rc62._marketing(policy))
    except Exception:
        pass
    if marketing:
        human = int(data.get("human_interest_score", 0) or 0); share = int(data.get("friend_share_score", 0) or 0)
        creative = int(data.get("creative_surprise_score", 0) or 0); mechanic = int(data.get("marketing_mechanic_score", 0) or 0)
        hook = " ".join(str(data.get("non_marketer_hook") or "").split())
        if fit >= 42 and hook and (human >= 58 or mechanic >= 62 or creative >= 64 or (share >= 52 and human >= 52)):
            data["decision"] = "publish"
            data["reason"] = f"RC66 POOL_ADMISSION: fit={fit}, human={human}, share={share}, creative={creative}, mechanic={mechanic}. Старий селектор: {reason[:320]}"
    elif fit >= 68:
        data["decision"] = "publish"
        data["reason"] = f"RC66 POOL_ADMISSION: релевантний fit={fit} допущено до READY-пулу. Старий селектор: {reason[:360]}"
    return result, data


def _published_today(rows: Iterable[Any], now: datetime) -> list[Any]:
    out = []
    for row in rows:
        try:
            dt = datetime.fromisoformat(str(v(row, "published_at", "") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(now.tzinfo).date() == now.date():
                out.append(row)
        except Exception:
            pass
    return out


def editorial_hold_reason(channel: Any, tags: StoryTags, recent: list[Any], *, now: datetime | None = None) -> str:
    if not bool(getattr(channel, "topic_balance_enabled", True)):
        return ""
    current = now or datetime.now().astimezone()
    limit = max(1, int(getattr(channel, "topic_daily_limit", 2) or 2))
    count = sum(1 for row in _published_today(recent, current) if tags.major != "Other" and row_tags(None, row, channel, persist=False).major == tags.major)
    if tags.major != "Other" and count >= limit:
        return f"topic_daily_cap:{tags.major}:{count}/{limit}"
    spacing = max(0, int(getattr(channel, "related_spacing_posts", 5) or 0))
    for row in recent[:spacing]:
        if related(tags, row_tags(None, row, channel, persist=False)):
            return f"related_spacing:{tags.minor or tags.major}:need_{spacing}_other_posts"
    return ""


def _recent(db: Any, channel_id: int, limit: int = 120) -> list[Any]:
    with db.connect() as con:
        return con.execute(
            '''SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.status='published' ORDER BY a.published_at DESC,a.id DESC LIMIT ?''',
            (channel_id, max(1, limit)),
        ).fetchall()


def _ready(db: Any, channel_id: int, limit: int = 120) -> list[Any]:
    with db.connect() as con:
        return con.execute(
            '''SELECT a.*,s.name AS source_name,s.priority AS source_priority FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.status='ready' AND a.cluster_parent_id IS NULL
               ORDER BY COALESCE(a.source_published_at,a.discovered_at) DESC,a.id DESC LIMIT ?''',
            (channel_id, max(1, limit)),
        ).fetchall()


def _too_old(row: Any, hours: int) -> bool:
    raw = str(v(row, "source_published_at", "") or "")
    if not raw:
        return False
    try:
        dt = parsedate_to_datetime(raw) if "," in raw or "GMT" in raw.upper() else datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc) < datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    except Exception:
        return False


def _caption(body: str, urls: list[str], *, video_link: str = "", hard_limit: int = 900) -> tuple[str, str]:
    from .telegram import build_post_text
    body = str(body or "").strip() + (f"\n\n🎬 Відео: {video_link}" if video_link else "")
    if len(urls) <= 1:
        url = urls[0] if urls else ""
        return build_post_text(body, source_url=url, include_source_link=bool(url), hard_limit=hard_limit), url
    footer = "\n\nДжерела:\n" + "\n".join(f"{i}. {url}" for i, url in enumerate(urls, 1))
    if len(body) + len(footer) > hard_limit:
        allowance = max(260, hard_limit - len(footer)); trimmed = body[:allowance].rstrip()
        cut = max(trimmed.rfind(". "), trimmed.rfind("! "), trimmed.rfind("? "), trimmed.rfind("… "))
        body = trimmed[:cut + 1] if cut >= max(120, allowance // 2) else trimmed
    result = body.rstrip() + footer
    if len(result) > hard_limit:
        raise RuntimeError(f"RC66 multisource caption exceeds {hard_limit} chars")
    return result, ""


def _publish_one(service: Any, channel: Any, row: Any) -> bool:
    from . import service as svc
    from .media_pipeline import prepare_article_media
    from .secrets_store import load_secrets
    from .telegram import TelegramError
    aid = int(v(row, "id", 0) or 0); fresh = service.db.get_article(aid)
    if fresh is None:
        return False
    body = str(v(fresh, "teaser_text", "") or "").strip(); issue = structural_issue(body)
    if issue:
        service.db.schedule_retry(aid, f"RC66 FINAL STRUCTURE BLOCK before Telegram: {issue}"); service._audit("rc66_final_gate", "retry", issue, channel_id=int(channel.id), article_id=aid); return False
    media = prepare_article_media(service.db.article_layout_json(fresh), service.db.media_urls(fresh), title=str(v(fresh, "title", "")), article_text=str(v(fresh, "raw_text", "")), marketing_context=svc._marketing_media_context(channel))
    if media.telegram_hero is None and media.telegram_direct_video is None:
        service.db.schedule_retry(aid, "RC66 ready publish: media disappeared"); return False
    urls = source_urls(service.db, fresh); caption, clickable = _caption(body, urls, video_link=str(media.video_link or ""), hard_limit=svc.MEDIA_POST_HARD_LIMIT)
    secrets = load_secrets(); token = secrets.channel_bot_tokens.get(str(channel.id), "") or secrets.default_telegram_bot_token
    service.db.update_article(aid, status="telegram_writing", rewrite_text=caption)
    try:
        if media.telegram_direct_video is not None:
            result = _PREV["send_video"](token, channel.telegram_chat_id, caption, media.telegram_direct_video.url, source_url=clickable)
        else:
            hero = media.telegram_hero
            result = _PREV["send_photo"](token, channel.telegram_chat_id, caption, filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=clickable)
    except TelegramError as exc:
        if exc.media_rejected and media.telegram_direct_video is not None and media.telegram_hero is not None:
            hero = media.telegram_hero
            result = _PREV["send_photo"](token, channel.telegram_chat_id, caption, filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=clickable)
        else:
            raise
    _PREV["update_article"](service.db, aid, status="published", published_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), telegram_message_id=result.message_id, telegram_media_count=result.media_count, retry_count=0, next_retry_at=None, last_error=None, reject_reason=None)
    with service.db.connect() as con:
        con.execute("UPDATE articles SET ready_at=NULL WHERE id=?", (aid,))
    service._audit("telegram", "published", f"RC66 READY; message_id={result.message_id}; sources={len(urls)}", channel_id=int(channel.id), article_id=aid)
    service._emit("publish", f"{channel.name}: опубліковано #{aid} з READY-пулу, Telegram {result.message_id}")
    return True


def _publish_ready(service: Any, channel: Any) -> None:
    if not publication_window_open(channel) or not _gap_ok(service, channel):
        return
    recent = _recent(service.db, int(channel.id)); posted = 0; limit = max(1, int(channel.max_posts_per_cycle or 3))
    for row in _ready(service.db, int(channel.id)):
        if posted >= limit:
            break
        aid = int(v(row, "id", 0) or 0)
        if _too_old(row, int(channel.max_age_hours or 24)):
            service.db.update_article(aid, status="rejected", reject_reason=f"RC66 READY expired: матеріал старіший за {int(channel.max_age_hours or 24)} год."); continue
        hold = editorial_hold_reason(channel, row_tags(service.db, row, channel), recent)
        if hold:
            service._audit("rc66_scheduler", "hold", hold, channel_id=int(channel.id), article_id=aid); continue
        try:
            if _publish_one(service, channel, row):
                posted += 1; recent = _recent(service.db, int(channel.id))
                if not bool(getattr(channel, "publish_immediately", False)):
                    break
        except Exception as exc:
            status = service.db.schedule_retry(aid, str(exc)); service._audit("rc66_publish", status, str(exc), channel_id=int(channel.id), article_id=aid); service._emit("error", f"{channel.name}: READY #{aid} ({status}): {exc}")
            if not bool(getattr(channel, "publish_immediately", False)):
                break


def _process(service: Any, channel: Any) -> None:
    prepare_clusters(service, channel)
    _CONTEXT.preparing = True
    try:
        _PREV["process"](service, channel)
    finally:
        _CONTEXT.preparing = False
    _publish_ready(service, channel)


def _db_init(db: Any) -> None:
    _PREV["db_init"](db)
    with db.connect() as con:
        for name, decl in (
            ("poll_immediate", "INTEGER NOT NULL DEFAULT 0"), ("publish_24h", "INTEGER NOT NULL DEFAULT 0"),
            ("publish_start", "TEXT NOT NULL DEFAULT '07:00'"), ("publish_end", "TEXT NOT NULL DEFAULT '00:00'"),
            ("publish_immediately", "INTEGER NOT NULL DEFAULT 0"), ("topic_balance_enabled", "INTEGER NOT NULL DEFAULT 1"),
            ("topic_daily_limit", "INTEGER NOT NULL DEFAULT 2"), ("related_spacing_posts", "INTEGER NOT NULL DEFAULT 5"),
            ("channel_mode", "TEXT NOT NULL DEFAULT 'editorial'"),
        ):
            db._ensure_column(con, "channels", name, decl)
        for name, decl in (
            ("tags_json", "TEXT NOT NULL DEFAULT '{}'"), ("topic_major", "TEXT NOT NULL DEFAULT ''"), ("topic_minor", "TEXT NOT NULL DEFAULT ''"),
            ("event_cluster_id", "INTEGER"), ("cluster_parent_id", "INTEGER"), ("ready_at", "TEXT"),
        ):
            db._ensure_column(con, "articles", name, decl)
        con.executescript('''
            CREATE TABLE IF NOT EXISTS event_clusters (id INTEGER PRIMARY KEY AUTOINCREMENT,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,cluster_key TEXT NOT NULL,canonical_article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS event_relations (channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,article_low INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,article_high INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,relation TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',checked_at TEXT NOT NULL,PRIMARY KEY(channel_id,article_low,article_high));
            CREATE INDEX IF NOT EXISTS idx_event_clusters_channel ON event_clusters(channel_id,id DESC);
            CREATE INDEX IF NOT EXISTS idx_event_relations_checked ON event_relations(channel_id,checked_at DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_ready ON articles(channel_id,status,ready_at);
            CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(event_cluster_id,id);
            CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(channel_id,topic_major,topic_minor,published_at);
        ''')


def _save_settings(db: Any, channel_id: int, *, poll_immediate=False, publish_24h=False, publish_start="07:00", publish_end="00:00", publish_immediately=False, topic_balance_enabled=True, topic_daily_limit=2, related_spacing_posts=5, channel_mode="editorial") -> None:
    mode = "monitoring" if str(channel_mode).casefold().startswith("monitor") else "editorial"
    with db.connect() as con:
        con.execute(
            '''UPDATE channels SET poll_immediate=?,publish_24h=?,publish_start=?,publish_end=?,publish_immediately=?,topic_balance_enabled=?,topic_daily_limit=?,related_spacing_posts=?,channel_mode=?,updated_at=? WHERE id=?''',
            (int(bool(poll_immediate)), int(bool(publish_24h)), _validate_hhmm(publish_start, "07:00"), _validate_hhmm(publish_end, "00:00"), int(bool(publish_immediately)), int(bool(topic_balance_enabled)), max(1, int(topic_daily_limit)), max(0, int(related_spacing_posts)), mode, datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), int(channel_id)),
        )


def install_rc66_editorial_queue() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import rc38_policy as rc38, rc59_universal_policy as rc59, rc65_universal_final_editor as rc65, service as svc
    from .database import Database
    _PREV.update(db_init=Database._init, pending=Database.pending_articles, update_article=Database.update_article, process=svc.AutopilotService._process, run_channel=svc.AutopilotService._run_channel, gap=svc.AutopilotService._gap_ok, audit=svc.AutopilotService._audit, emit=svc.AutopilotService._emit, send_photo=svc.send_prepared_photo, send_video=svc.send_video_url, final_edit=rc65._universal_final_edit, selector=rc59._run_selector)
    Database._init = _db_init; Database.pending_articles = _pending; Database.update_article = _update_article; Database.rc66_save_channel_settings = _save_settings
    svc.AutopilotService._run_channel = _run_channel; svc.AutopilotService._gap_ok = _gap_ok; svc.AutopilotService._process = _process; svc.AutopilotService._audit = _audit; svc.AutopilotService._emit = _emit
    svc.send_prepared_photo = _send_photo; svc.send_video_url = _send_video
    rc38.topic_balance_reject_reason = lambda *_a, **_k: ""; rc59._run_selector = _selector; rc65._universal_final_edit = _final_edit
    LOG.info("RC66 installed: READY pool, tags/event clusters, AI dedupe/update, per-channel schedules, daily topic caps, related spacing, hard final structure gate")
    _INSTALLED = True
