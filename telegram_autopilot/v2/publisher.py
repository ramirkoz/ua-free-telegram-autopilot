from __future__ import annotations

import json
import re
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any, Callable

from ..secrets_store import load_secrets
from ..fact_guard import strip_non_actionable_article_urls
from ..facebook import FacebookError, publish_page_link
from ..telegram import (
    TelegramError,
    prepare_telegram_media_list,
    send_prepared_media_only,
)
from .source_attribution import attribution_for_article
from .domain import BlockedBy, ChannelMode, EditorialRuntimeProfile
from .loghub import event
from .media_pipeline import build_publication_media_bundle, media_bundle_complete
from .storage import V2Store, now_iso
from .telegram_attribution import (
    build_attributed_post_text,
    send_prepared_media_group_attributed,
    send_prepared_publication_attributed,
    send_text_attributed,
)
from .urlnorm import normalize_url


def _parse_time(value: str, fallback: dt_time) -> dt_time:
    try:
        hour, minute = str(value or "").split(":", 1)
        return dt_time(max(0, min(23, int(hour))), max(0, min(59, int(minute))))
    except Exception:
        return fallback


def _inside_window(start: str, end: str, now: datetime | None = None) -> bool:
    local = now or datetime.now().astimezone()
    current = local.time().replace(second=0, microsecond=0)
    a = _parse_time(start, dt_time(7, 0)); b = _parse_time(end, dt_time(0, 0))
    if a == b:
        return True
    if a < b:
        return a <= current < b
    return current >= a or current < b


def _last_gap_ok(last_iso: str, minutes: int) -> bool:
    if not last_iso:
        return True
    try:
        dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt.astimezone(timezone.utc) >= timedelta(minutes=max(0, int(minutes)))
    except Exception:
        return True



_VIDEO_EXPECTED_WORDS = (
    "video", "trailer", "teaser", "clip", "footage", "commercial", "spot", "campaign film",
    "відео", "відеоролик", "ролик", "трейлер", "тизер", "рекламний ролик",
)


def _video_expected(article: Any) -> bool:
    text = (str(article["title"] or "") + "\n" + str(article["raw_text"] or "")[:3500] + "\n" + str(article["final_text"] or "")[:1800]).casefold()
    return any(word in text for word in _VIDEO_EXPECTED_WORDS)

def _telegram_video_recovery(article: Any) -> str:
    try:
        layout = json.loads(str(article["article_layout_json"] or "{}"))
    except Exception:
        return ""
    if not isinstance(layout, dict):
        return ""
    tg = layout.get("telegram")
    return str(tg.get("video_recovery") or "") if isinstance(tg, dict) else ""

def _web_media_provenance(article: Any) -> str:
    try:
        layout = json.loads(str(article["article_layout_json"] or "{}"))
    except Exception:
        return ""
    if not isinstance(layout, dict):
        return ""
    meta = layout.get("featured_meta")
    return str(meta.get("provenance") or "") if isinstance(meta, dict) else ""


_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)", re.IGNORECASE)
_BARE_LINK_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_URL_TRAILING_PUNCT = ").,;:!?»]}"
_EMPTY_PROMO_LINE_RE = re.compile(
    r"(?iu)^\s*(?:детальніше|детали|деталі(?:/реєстрація)?|реєстрація|registration|read more|посилання)\s*[:：-]?\s*$"
)


def _strip_all_publication_links(text: str) -> str:
    """Remove clickable/bare URLs while preserving useful linked anchor text."""
    value = _MARKDOWN_LINK_RE.sub(lambda match: str(match.group(1) or "").strip(), str(text or ""))

    def strip_bare(match: re.Match[str]) -> str:
        token = str(match.group(0) or "")
        trailing = ""
        while token and token[-1] in _URL_TRAILING_PUNCT:
            trailing = token[-1] + trailing
            token = token[:-1]
        return trailing

    value = _BARE_LINK_RE.sub(strip_bare, value)
    value = re.sub(r"\(\s*\)", "", value)
    lines: list[str] = []
    for raw in value.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _EMPTY_PROMO_LINE_RE.fullmatch(line):
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def _source_urls(article: Any) -> list[str]:
    """Return canonical attribution URLs, preserving the primary source first."""
    urls: list[str] = []
    primary = normalize_url(str(article["canonical_source_url"] or article["source_url"] or "").strip())
    if primary.startswith(("http://", "https://")):
        urls.append(primary)
    try:
        layout = json.loads(str(article["article_layout_json"] or "{}"))
    except Exception:
        layout = {}
    candidates: list[Any] = []
    if isinstance(layout, dict):
        for key in ("source_urls", "sources", "evidence_sources"):
            value = layout.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        tg = layout.get("telegram")
        if isinstance(tg, dict):
            value = tg.get("source_urls")
            if isinstance(value, list):
                candidates.extend(value)
    for item in candidates:
        value = (item.get("url") or item.get("source_url")) if isinstance(item, dict) else item
        url = normalize_url(str(value or "").strip())
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls[:8]


def _telegram_post_url(chat_id: str, message_id: str) -> str:
    target = str(chat_id or "").strip()
    mid = str(message_id or "").strip()
    if not target or not mid:
        return ""
    if target.startswith("@") and len(target) > 1:
        return f"https://t.me/{target[1:]}/{mid}"
    if target.startswith("https://t.me/") or target.startswith("http://t.me/"):
        base = target.rstrip("/").split("?", 1)[0]
        return f"{base}/{mid}"
    if target.startswith("-100") and target[4:].isdigit():
        return f"https://t.me/c/{target[4:]}/{mid}"
    if target and not target.lstrip("-").isdigit() and all(ch.isalnum() or ch == "_" for ch in target):
        return f"https://t.me/{target}/{mid}"
    return ""


def _facebook_message(text: str, telegram_post_url: str) -> str:
    body = str(text or "").strip()
    link = str(telegram_post_url or "").strip()
    if not link:
        return body
    return f"{body}\n\nДжерело: {link}".strip()


class Publisher:
    def __init__(self, store: V2Store):
        self.store = store

    def _media_recovery_plan(self, article: Any, bundle: Any, *, video_expected: bool = False) -> tuple[str, int | None, int]:
        """Classify missing required media as recoverable/probe/permanent."""
        article_id = int(article["id"] or 0)
        try:
            layout = json.loads(str(article["article_layout_json"] or "{}"))
        except Exception:
            layout = {}
        if not isinstance(layout, dict):
            layout = {}
        recovery = layout.get("media_recovery")
        if not isinstance(recovery, dict):
            recovery = {}
        attempts = int(recovery.get("attempts") or 0) + 1
        provenance = _web_media_provenance(article)
        source_kind = str(getattr(bundle, "source_kind", "") or "").casefold()
        source_media_count = int(getattr(bundle, "source_media_count", 0) or getattr(bundle, "declared_media_count", 0) or 0)
        strong_recoverable = bool(
            source_media_count > 0 or video_expected or source_kind == "telegram" or
            provenance in {"body", "jsonld_article_image", "og_image", "twitter_image"}
        )
        max_attempts = 4 if strong_recoverable else 2
        if attempts <= max_attempts:
            classification = "recoverable" if strong_recoverable else "probe"
            retry_seconds = min(7200, 600 * (2 ** min(3, attempts - 1)))
        else:
            classification = "permanent"
            retry_seconds = None
        recovery.update({
            "attempts": attempts,
            "classification": classification,
            "last_attempt_at": now_iso(),
            "source_media_count": source_media_count,
            "provenance": provenance,
            "video_expected": bool(video_expected),
            "next_retry_seconds": retry_seconds or 0,
        })
        layout["media_recovery"] = recovery
        self.store.update_article(article_id, article_layout_json=json.dumps(layout, ensure_ascii=False, separators=(",", ":")))
        return classification, retry_seconds, attempts

    def _queue_facebook_after_telegram(self, article_id: int, channel: Any, message_id: str) -> None:
        page_ids = [str(x).strip() for x in (getattr(channel, "facebook_page_ids", []) or []) if str(x).strip()]
        if not page_ids:
            return
        telegram_url = _telegram_post_url(str(channel.telegram_chat_id or ""), str(message_id or ""))
        if not telegram_url:
            event(
                "facebook", "facebook repost skipped: telegram public link unavailable", level=30,
                channel_id=int(channel.id), article_id=int(article_id), telegram_chat_id=str(channel.telegram_chat_id or ""),
            )
            return
        try:
            queued = self.store.queue_facebook_reposts(
                article_id, int(channel.id), page_ids, telegram_message_id=str(message_id), telegram_post_url=telegram_url,
            )
            event(
                "facebook", "facebook reposts queued", channel_id=int(channel.id), article_id=int(article_id),
                pages=queued, telegram_post_url=telegram_url,
            )
            self.publish_pending_facebook(int(channel.id), limit=max(1, min(8, queued or 1)))
        except Exception as exc:
            event(
                "facebook", "facebook queue failed after telegram publish", level=40,
                channel_id=int(channel.id), article_id=int(article_id), detail=str(exc)[:1000],
            )

    def _mark_published(
        self, article_id: int, channel: Any, *, message_id: str, media_count: int = 0,
        message_ids: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.store.mark_published(
            article_id, message_id=str(message_id), media_count=int(media_count), message_ids=message_ids,
        )
        self._queue_facebook_after_telegram(article_id, channel, str(message_id))

    def _delivery_preflight(self, article_id: int, channel: Any) -> str:
        journal = self.store.delivery_journal(article_id)
        if not journal:
            return "CONTINUE"
        state = str(journal.get("state") or "")
        complete = bool(int(journal.get("complete") or 0))
        if state == "COMMITTED":
            row = self.store.get_article(article_id)
            return "PUBLISHED" if row is not None and str(row["stage"]) == str(Stage.PUBLISHED) else "DELIVERY_COMMITTED"
        if state == "ACKNOWLEDGED":
            message_id = str(journal.get("primary_message_id") or "")
            try:
                message_ids = json.loads(str(journal.get("message_ids_json") or "[]"))
            except Exception:
                message_ids = []
            clean_ids = [str(x) for x in message_ids if str(x).strip()] if isinstance(message_ids,list) else []
            if complete and message_id:
                self._mark_published(
                    article_id, channel, message_id=message_id, media_count=int(journal.get("media_count") or 0),
                    message_ids=clean_ids or None,
                )
                event("publish", "recovered acknowledged delivery after restart", channel_id=int(channel.id), article_id=article_id, message_id=message_id)
                return "PUBLISHED"
            if clean_ids:
                self.store.record_telegram_media_delivery(article_id, clean_ids, caption_attached=False, caption_message_id="")
                event("publish", "recovered partial media delivery journal", channel_id=int(channel.id), article_id=article_id, published_media_count=len(clean_ids))
        if state in {"SENDING", "UNKNOWN"}:
            detail = str(journal.get("last_error") or "Delivery was in-flight when the previous process stopped; Telegram outcome is unknown.")
            self.store.fail_delivery(article_id, detail, outcome_unknown=True)
            self.store.publication_backoff(
                article_id, blocked_by=BlockedBy.TELEGRAM, error_code="DELIVERY_OUTCOME_UNKNOWN", detail=detail, retry_seconds=None, count_attempt=False,
            )
            event("publish", "durable delivery outcome unknown; blind retry blocked", level=40, channel_id=int(channel.id), article_id=article_id)
            return "DELIVERY_OUTCOME_UNKNOWN"
        return "CONTINUE"

    def _delivery_sending(self, article_id: int, *, mode: str, expected_media_count: int = 0) -> None:
        self.store.mark_delivery_sending(article_id, mode=mode, expected_media_count=expected_media_count)

    def _delivery_ack(
        self, article_id: int, *, message_id: str, message_ids: list[str] | tuple[str, ...], media_count: int,
        complete: bool, mode: str, expected_media_count: int = 0,
    ) -> None:
        self.store.acknowledge_delivery(
            article_id, message_id=message_id, message_ids=message_ids, media_count=media_count, complete=complete,
            mode=mode, expected_media_count=expected_media_count,
        )

    def publish_pending_facebook(self, channel_id: int, *, limit: int = 6) -> int:
        rows = self.store.pending_facebook_reposts(channel_id, limit=max(1, int(limit)))
        if not rows:
            return 0
        try:
            secrets = load_secrets()
        except Exception as exc:
            event("facebook", "facebook secrets unavailable", level=40, channel_id=channel_id, detail=str(exc)[:800])
            return 0
        page_map = {
            str(item.get("id") or "").strip(): dict(item)
            for item in (getattr(secrets, "facebook_pages", []) or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        version = str(getattr(secrets, "facebook_graph_version", "v26.0") or "v26.0").strip() or "v26.0"
        published = 0
        for row in rows:
            article_id = int(row["article_id"] or 0)
            page_id = str(row["page_id"] or "").strip()
            page = page_map.get(page_id)
            if not page:
                retry_at = self.store.mark_facebook_repost_failed(
                    article_id, page_id, "Facebook Page credential відсутній у зашифрованих налаштуваннях", retryable=False,
                )
                event(
                    "facebook", "facebook page credential missing", level=30, channel_id=channel_id,
                    article_id=article_id, page_id=page_id, next_retry_at=retry_at,
                )
                continue
            token = str(page.get("access_token") or "").strip()
            page_name = str(page.get("name") or page_id).strip() or page_id
            message = _facebook_message(str(row["final_text"] or ""), str(row["telegram_post_url"] or ""))
            try:
                post_id = publish_page_link(
                    page_id, token, message=message, telegram_post_url=str(row["telegram_post_url"] or ""),
                    graph_version=version,
                )
            except FacebookError as exc:
                retry_at = self.store.mark_facebook_repost_failed(
                    article_id, page_id, str(exc), retryable=bool(exc.retryable),
                )
                event(
                    "facebook", "facebook repost failed", level=30 if exc.retryable else 40,
                    channel_id=channel_id, article_id=article_id, page_id=page_id, page_name=page_name,
                    retryable=exc.retryable, code=exc.code, next_retry_at=retry_at, detail=str(exc)[:1000],
                )
                continue
            except Exception as exc:
                retry_at = self.store.mark_facebook_repost_failed(article_id, page_id, str(exc), retryable=True)
                event(
                    "facebook", "facebook repost exception", level=40, channel_id=channel_id,
                    article_id=article_id, page_id=page_id, page_name=page_name, next_retry_at=retry_at, detail=str(exc)[:1000],
                )
                continue
            self.store.mark_facebook_repost_done(article_id, page_id, post_id)
            published += 1
            event(
                "facebook", "facebook repost published", channel_id=channel_id, article_id=article_id,
                page_id=page_id, page_name=page_name, facebook_post_id=post_id,
                telegram_post_url=str(row["telegram_post_url"] or ""),
            )
        return published

    def can_publish_now(self, channel_id: int) -> tuple[bool, str]:
        channel = self.store.get_channel(channel_id)
        if channel is None:
            return False, "CHANNEL_MISSING"
        if not channel.enabled:
            return False, "CHANNEL_DISABLED"
        if not channel.publish_24h and not _inside_window(channel.publish_start, channel.publish_end):
            return False, "OUTSIDE_WINDOW"
        # RC110: a durable human approval is editorial intent, not ordinary READY
        # inventory. Catch-up keeps the configured publication window but reduces
        # the spacing to one minute so multi-day approved backlogs drain promptly
        # without dumping a burst of posts in one loop.
        gap_minutes = 1 if bool(getattr(self, "_rc110_human_catchup", False)) else channel.min_publish_interval_minutes
        if not _last_gap_ok(self.store.last_published_at(channel_id), gap_minutes):
            return False, "MIN_INTERVAL"
        return True, "OK"

    def _telegram_failure(self, article_id: int, channel_id: int, exc: TelegramError) -> str:
        if exc.outcome_unknown:
            # Retrying an unknown outcome can duplicate a real Telegram post. Keep it
            # blocked until a human/source refresh resolves the ambiguity.
            self.store.publication_backoff(
                article_id, blocked_by=BlockedBy.TELEGRAM, error_code="TELEGRAM_OUTCOME_UNKNOWN",
                detail=str(exc), retry_seconds=None,
            )
            event("publish", "telegram outcome unknown", level=40, channel_id=channel_id, article_id=article_id, detail=str(exc))
            return "TELEGRAM_OUTCOME_UNKNOWN"
        code = "TELEGRAM_RETRY" if exc.retryable else "TELEGRAM_REJECTED"
        retry_seconds = 180 if exc.retryable else None
        retry_at = self.store.publication_backoff(
            article_id, blocked_by=BlockedBy.TELEGRAM, error_code=code, detail=str(exc),
            retry_seconds=retry_seconds,
        )
        event(
            "publish", "telegram publication failed", level=40, channel_id=channel_id, article_id=article_id,
            detail=str(exc), retryable=exc.retryable, next_retry_at=retry_at,
        )
        return code

    def publish_one(self, article_id: int, heartbeat: Callable[[], None] | None = None) -> str:
        ok, reason = self.store.publication_guard(article_id)
        if not ok:
            if reason == "SOURCE_MISSING":
                self.store.block_article(article_id, blocked_by=BlockedBy.SOURCE, error_code=reason, detail="Немає canonical source URL")
            elif reason == "TEXT_MISSING":
                self.store.block_article(article_id, blocked_by=BlockedBy.QUALITY, error_code=reason, detail="Порожній final_text")
            elif reason.startswith("ALREADY_PUBLISHED:"):
                try: duplicate_of = int(reason.split(":", 1)[1])
                except Exception: duplicate_of = 0
                if duplicate_of > 0:
                    row = self.store.get_article(article_id)
                    self.store.mark_duplicate(article_id, duplicate_of, f"Already published normalized URL as article #{duplicate_of}")
                    event("publish", "duplicate publication blocked", level=30, channel_id=int(row["channel_id"] if row else 0), article_id=article_id, duplicate_of=duplicate_of)
                return "DUPLICATE_PUBLISHED"
            return reason

        article = self.store.get_article(article_id)
        if article is None:
            raise KeyError(article_id)
        channel_id = int(article["channel_id"])
        channel = self.store.get_channel(channel_id)
        if channel is None:
            raise ValueError("CHANNEL_MISSING")
        delivery_preflight = self._delivery_preflight(article_id, channel)
        if delivery_preflight != "CONTINUE":
            return delivery_preflight
        current_text = str(article["final_text"] or "").strip()
        strip_body_links = self.store.source_strip_body_links(int(article["source_id"]))
        if strip_body_links:
            sanitized = _strip_all_publication_links(current_text)
            if sanitized != current_text:
                current_text = sanitized
                self.store.update_article(article_id, final_text=current_text)
                article = self.store.get_article(article_id) or article
                event(
                    "publish", "source setting removed URLs from article body",
                    channel_id=channel_id, article_id=article_id, source_id=int(article["source_id"]),
                )
        if channel.mode == ChannelMode.MONITORING:
            sanitized = strip_non_actionable_article_urls(article, current_text)
            if sanitized != current_text:
                current_text = sanitized
                self.store.update_article(article_id, final_text=current_text)
                article = self.store.get_article(article_id) or article
                event(
                    "publish", "removed non-actionable source/media URL from body",
                    channel_id=channel_id, article_id=article_id,
                )
        # Local import avoids publisher <-> semantic/editorial module cycles while
        # keeping the current channel rules authoritative at the last boundary.
        from .editorial import prepublish_quality_issues
        qa_issues = prepublish_quality_issues(channel, article, current_text)
        if qa_issues:
            detail = "; ".join(qa_issues[:6])
            outcome = self.store.requeue_quality_rewrite(
                article_id, error_code="PREPUBLISH_QA", detail=detail, max_attempts=3
            )
            event(
                "publish", "pre-publish QA blocked READY article", level=30,
                channel_id=channel_id, article_id=article_id, outcome=outcome, detail=detail[:1200],
            )
            return outcome
        schedule_ok, schedule_reason = self.can_publish_now(channel_id)
        if not schedule_ok:
            return schedule_reason

        source_urls = _source_urls(article)
        source_url = source_urls[0] if source_urls else ""
        if not source_url.startswith(("http://", "https://")):
            self.store.block_article(article_id, blocked_by=BlockedBy.SOURCE, error_code="SOURCE_MISSING", detail="Немає canonical source URL")
            return "SOURCE_MISSING"
        attribution_urls, attribution_labels = attribution_for_article(
            channel,
            article,
            source_url=source_url,
            source_urls=source_urls,
        )

        bundle = build_publication_media_bundle(channel, article)
        # RC56: if the story is actually about a video, a YouTube/Vimeo embed must
        # remain reachable from the Telegram post even when Telegram receives only a
        # preview image.  Add the canonical video as a dedicated clickable footer.
        if bundle.video_link and bundle.video_link not in attribution_urls:
            if attribution_labels is None:
                count = len(attribution_urls)
                attribution_labels = [
                    "Джерело" if count == 1 else f"Джерело {idx + 1}"
                    for idx in range(count)
                ]
            attribution_urls = [*attribution_urls, bundle.video_link]
            attribution_labels = [*list(attribution_labels or []), "🎬 Відео"]
            event("media", "video link attached to publication", channel_id=channel_id, article_id=article_id, video_url=bundle.video_link)
        else:
            try:
                commercial_editorial = EditorialRuntimeProfile(str(channel.editorial_runtime_profile)) == EditorialRuntimeProfile.COMMERCIAL_EDITORIAL
            except Exception:
                commercial_editorial = False
            if commercial_editorial and _video_expected(article):
                event("media", "VIDEO_EXPECTED_BUT_NOT_FOUND", level=30, channel_id=channel_id, article_id=article_id, source_url=source_url)

        text = str(article["final_text"] or "").strip()
        try:
            post_text = build_attributed_post_text(
                text,
                source_url=source_url,
                source_urls=attribution_urls,
                source_labels=attribution_labels,
                include_source_link=True,
                hard_limit=900,
            )
        except TelegramError as exc:
            detail = str(exc)
            if "перевищує ліміт" in detail.casefold():
                outcome = self.store.requeue_quality_rewrite(article_id, error_code="TELEGRAM_OVERSIZE", detail=detail, max_attempts=3)
                event("publish", "oversize article removed from READY and queued for rewrite", level=30, channel_id=channel_id, article_id=article_id, chars=len(text), outcome=outcome)
                return outcome
            self.store.block_article(article_id, blocked_by=BlockedBy.QUALITY, error_code="TELEGRAM_TEXT_INVALID", detail=detail)
            return "TELEGRAM_TEXT_INVALID"

        policy = channel.policy.normalized_media_policy()
        source_media_count = int(bundle.source_media_count or bundle.declared_media_count or bundle.count)
        video_recovery = _telegram_video_recovery(article)
        event(
            "media", "publication media gate", channel_id=channel_id, article_id=article_id,
            media_policy=policy, source_media_count=source_media_count,
            bundle_media_count=bundle.count, declared_media_count=bundle.declared_media_count,
            source_kind=bundle.source_kind, stitched=bundle.stitched,
            telegram_video_recovery=video_recovery, web_media_provenance=_web_media_provenance(article),
            gallery_detected=bool(getattr(bundle,"gallery_detected",False)),
            gallery_items_found=int(getattr(bundle,"gallery_items_found",0) or 0),
            gallery_items_kept=int(getattr(bundle,"gallery_items_kept",0) or 0),
            video_embed_count=int(getattr(bundle,"video_embed_count",0) or 0),
            web_media_source=str(getattr(bundle,"web_media_source","") or ""),
        )
        if policy == "required" and not bundle.count:
            classification, retry_seconds, media_attempt = self._media_recovery_plan(article, bundle, video_expected=_video_expected(article))
            detail = f"Політика каналу вимагає валідне медіа; media_recovery={classification}; attempt={media_attempt}"
            self.store.publication_backoff(article_id, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_REQUIRED", detail=detail, retry_seconds=retry_seconds, count_attempt=False)
            event(
                "media", "required media missing at final publication gate", level=30, channel_id=channel_id, article_id=article_id,
                source_media_count=source_media_count, bundle_media_count=0, media_recovery=classification,
                media_recovery_attempt=media_attempt, retry_seconds=retry_seconds or 0,
            )
            return "MEDIA_REQUIRED"
        if policy == "required" and not media_bundle_complete(bundle):
            classification, retry_seconds, media_attempt = self._media_recovery_plan(article, bundle, video_expected=_video_expected(article))
            detail = f"Джерело має {source_media_count} медіа, але до publication bundle дійшло {bundle.count}; media_recovery={classification}; attempt={media_attempt}."
            self.store.publication_backoff(article_id, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_INCOMPLETE", detail=detail, retry_seconds=retry_seconds, count_attempt=False)
            event(
                "media", "required media bundle incomplete", level=40, channel_id=channel_id, article_id=article_id,
                source_media_count=source_media_count, bundle_media_count=bundle.count, media_recovery=classification,
                media_recovery_attempt=media_attempt, retry_seconds=retry_seconds or 0,
            )
            return "MEDIA_INCOMPLETE"

        secrets = load_secrets()
        token = str(secrets.channel_bot_tokens.get(str(channel_id)) or secrets.default_telegram_bot_token or "").strip()
        if not token or not channel.telegram_chat_id:
            self.store.publication_backoff(article_id, blocked_by=BlockedBy.CONFIG, error_code="TELEGRAM_CONFIG", detail="Не налаштовано bot token/Chat ID", retry_seconds=300, count_attempt=False)
            return "TELEGRAM_CONFIG"

        if heartbeat is not None:
            try: heartbeat()
            except Exception: pass

        # RC17 publication contract:
        #   * no media -> one normal text post;
        #   * one media -> one photo/video post with <=900-char caption;
        #   * 2..10 media -> one Telegram media group with the caption on the first item;
        #   * >10 media -> multiple groups; only the FINAL group carries the caption so
        #     the text remains visually below all preceding media.
        # Media policy (required/preferred/optional) is configured by the operator.
        if not bundle.count:
            self._delivery_sending(article_id, mode="text", expected_media_count=0)
            try:
                text_result = send_text_attributed(
                    token,
                    channel.telegram_chat_id,
                    post_text,
                    source_url=source_url,
                    source_urls=attribution_urls,
                    source_labels=attribution_labels,
                    timeout=45.0,
                )
            except TelegramError as exc:
                self.store.fail_delivery(article_id, str(exc), outcome_unknown=bool(getattr(exc, "outcome_unknown", False)))
                return self._telegram_failure(article_id, channel_id, exc)
            self._delivery_ack(article_id, message_id=text_result.message_id, message_ids=list(text_result.message_ids), media_count=0, complete=True, mode="text")
            self._mark_published(article_id, channel, message_id=text_result.message_id, media_count=0, message_ids=text_result.message_ids)
            event(
                "publish", "published text", channel_id=channel_id, article_id=article_id,
                message_id=text_result.message_id, message_ids=list(text_result.message_ids),
                media_policy=policy, source_media_count=source_media_count, bundle_media_count=0,
                published_media_count=0, media_outcome="NO_MEDIA", source_url=source_url,
            )
            return "PUBLISHED"

        # RC17: media is fetched by Autopilot first and uploaded as multipart files.
        # Telegram never receives third-party URLs, eliminating WEBPAGE_CURL_FAILED
        # from CDN/hotlink restrictions and letting us dedupe exact binary clones.
        prepared, prepare_failures = prepare_telegram_media_list(bundle.encoded_items, timeout=35.0, heartbeat=heartbeat)
        duplicate_binary_count = max(0, bundle.count - len(prepared) - len(prepare_failures))
        event(
            "media", "media prepared for telegram upload", channel_id=channel_id, article_id=article_id,
            media_policy=policy, source_media_count=source_media_count, bundle_media_count=bundle.count,
            prepared_media_count=len(prepared), failed_media_count=len(prepare_failures),
            binary_duplicates_removed=duplicate_binary_count, upload_mode="multipart_local",
            gallery_detected=bool(getattr(bundle,"gallery_detected",False)),
            gallery_items_found=int(getattr(bundle,"gallery_items_found",0) or 0),
            gallery_items_kept=int(getattr(bundle,"gallery_items_kept",0) or 0),
            video_embed_count=int(getattr(bundle,"video_embed_count",0) or 0),
        )

        if prepare_failures and policy == "required":
            retryable = any(exc.retryable for _, exc in prepare_failures)
            detail = "; ".join(str(exc) for _, exc in prepare_failures[:3])
            retry_at = self.store.publication_backoff(
                article_id, blocked_by=BlockedBy.MEDIA,
                error_code="MEDIA_DOWNLOAD_RETRY" if retryable else "MEDIA_DOWNLOAD_FAILED",
                detail=f"Не вдалося локально підготувати {len(prepare_failures)}/{bundle.count} медіа: {detail}",
                retry_seconds=600 if retryable else None,
            )
            event(
                "media", "required media download failed", level=40, channel_id=channel_id, article_id=article_id,
                source_media_count=source_media_count, bundle_media_count=bundle.count,
                prepared_media_count=len(prepared), failed_media_count=len(prepare_failures),
                retryable=retryable, next_retry_at=retry_at,
            )
            return "MEDIA_DOWNLOAD_RETRY" if retryable else "MEDIA_DOWNLOAD_FAILED"

        if not prepared:
            # Preferred/optional may intentionally degrade to text when media cannot
            # be fetched. Required was handled above and can never reach this branch.
            self._delivery_sending(article_id, mode="text_fallback", expected_media_count=0)
            try:
                text_result = send_text_attributed(
                    token,
                    channel.telegram_chat_id,
                    post_text,
                    source_url=source_url,
                    source_urls=attribution_urls,
                    source_labels=attribution_labels,
                    timeout=45.0,
                )
            except TelegramError as exc:
                self.store.fail_delivery(article_id, str(exc), outcome_unknown=bool(getattr(exc, "outcome_unknown", False)))
                return self._telegram_failure(article_id, channel_id, exc)
            self._delivery_ack(article_id, message_id=text_result.message_id, message_ids=list(text_result.message_ids), media_count=0, complete=True, mode="text_fallback")
            self._mark_published(article_id, channel, message_id=text_result.message_id, media_count=0, message_ids=text_result.message_ids)
            event(
                "publish", "published text after media preparation failure", level=30, channel_id=channel_id, article_id=article_id,
                message_id=text_result.message_id, media_policy=policy, source_media_count=source_media_count,
                bundle_media_count=bundle.count, prepared_media_count=0, failed_media_count=len(prepare_failures),
                published_media_count=0, media_outcome="TEXT_FALLBACK",
            )
            return "PUBLISHED"

        delivery_count = len(prepared)
        delivery = self.store.telegram_delivery_state(article_id)
        media_ids = [str(x) for x in delivery.get("media_message_ids", []) if str(x).strip()] if delivery else []
        delivery_mode = str(delivery.get("delivery_mode") or "") if delivery else ""
        caption_attached = bool(delivery.get("caption_attached")) if delivery else False
        caption_message_id = str(delivery.get("caption_message_id") or "") if delivery else ""

        if media_ids and delivery_mode != "caption_media_v1":
            detail = "Незавершена публікація старого формату: медіа вже відправлено, caption не підтверджено."
            self.store.publication_backoff(
                article_id, blocked_by=BlockedBy.MEDIA, error_code="LEGACY_MEDIA_PARTIAL", detail=detail, retry_seconds=None,
            )
            event("media", "legacy partial media delivery blocked", level=40, channel_id=channel_id, article_id=article_id, published_media_count=len(media_ids))
            return "LEGACY_MEDIA_PARTIAL"

        if caption_attached and len(media_ids) >= delivery_count and caption_message_id:
            self._mark_published(article_id, channel, message_id=caption_message_id, media_count=delivery_count, message_ids=media_ids[:delivery_count])
            event(
                "publish", "recovered completed captioned media publication", channel_id=channel_id, article_id=article_id,
                message_id=caption_message_id, published_media_count=delivery_count, upload_mode="multipart_local",
            )
            return "PUBLISHED"

        already_sent = min(len(media_ids), delivery_count)
        pending = list(prepared[already_sent:])
        sent_count = already_sent
        final_caption_message_id = ""
        while pending:
            chunk = pending[:10]
            is_final_chunk = sent_count + len(chunk) >= delivery_count
            self._delivery_sending(article_id, mode="media_final" if is_final_chunk else "media_chunk", expected_media_count=delivery_count)
            try:
                if len(chunk) == 1:
                    if is_final_chunk:
                        media_result = send_prepared_publication_attributed(
                            token,
                            channel.telegram_chat_id,
                            post_text,
                            chunk[0],
                            source_url=source_url,
                            source_urls=attribution_urls,
                            source_labels=attribution_labels,
                            timeout=75.0,
                        )
                    else:
                        media_result = send_prepared_media_only(token, channel.telegram_chat_id, chunk[0], timeout=75.0)
                else:
                    media_result = send_prepared_media_group_attributed(
                        token,
                        channel.telegram_chat_id,
                        chunk,
                        caption=post_text if is_final_chunk else "",
                        source_url=source_url if is_final_chunk else "",
                        source_urls=attribution_urls if is_final_chunk else None,
                        source_labels=attribution_labels if is_final_chunk else None,
                        timeout=90.0,
                    )
            except TelegramError as exc:
                self.store.fail_delivery(article_id, str(exc), outcome_unknown=bool(getattr(exc, "outcome_unknown", False)))
                published_media_count = len(media_ids)
                event(
                    "media", "local-upload media delivery failed", level=40, channel_id=channel_id, article_id=article_id,
                    media_policy=policy, source_media_count=source_media_count, bundle_media_count=bundle.count,
                    prepared_media_count=delivery_count, published_media_count=published_media_count,
                    media_outcome="REJECTED" if exc.media_rejected else "ERROR", detail=str(exc)[:800],
                )
                if exc.media_rejected and policy in {"preferred", "optional"} and not media_ids:
                    self._delivery_sending(article_id, mode="text_after_media_reject", expected_media_count=0)
                    try:
                        text_result = send_text_attributed(
                            token,
                            channel.telegram_chat_id,
                            post_text,
                            source_url=source_url,
                            source_urls=attribution_urls,
                            source_labels=attribution_labels,
                            timeout=45.0,
                        )
                    except TelegramError as text_exc:
                        self.store.fail_delivery(article_id, str(text_exc), outcome_unknown=bool(getattr(text_exc, "outcome_unknown", False)))
                        return self._telegram_failure(article_id, channel_id, text_exc)
                    self._delivery_ack(article_id, message_id=text_result.message_id, message_ids=list(text_result.message_ids), media_count=0, complete=True, mode="text_after_media_reject")
                    self._mark_published(article_id, channel, message_id=text_result.message_id, media_count=0, message_ids=text_result.message_ids)
                    event(
                        "publish", "published text after preferred/optional local media rejection", level=30,
                        channel_id=channel_id, article_id=article_id, message_id=text_result.message_id,
                        source_media_count=source_media_count, bundle_media_count=bundle.count,
                        prepared_media_count=delivery_count, published_media_count=0, media_outcome="TEXT_FALLBACK",
                    )
                    return "PUBLISHED"

                retry_at = self.store.publication_backoff(
                    article_id, blocked_by=BlockedBy.MEDIA,
                    error_code="MEDIA_UPLOAD_RETRY" if exc.retryable else ("MEDIA_PARTIAL" if media_ids else "MEDIA_UPLOAD_REJECTED"),
                    detail=(f"Опубліковано {len(media_ids)}/{delivery_count} медіа; " if media_ids else "") + str(exc),
                    retry_seconds=300 if exc.retryable else None,
                )
                event(
                    "media", "media publication backoff armed", level=40, channel_id=channel_id, article_id=article_id,
                    retryable=exc.retryable, next_retry_at=retry_at, published_media_count=len(media_ids),
                    expected_media_count=delivery_count,
                )
                return "MEDIA_UPLOAD_RETRY" if exc.retryable else ("MEDIA_PARTIAL" if media_ids else "MEDIA_UPLOAD_REJECTED")

            new_ids = [str(x) for x in media_result.message_ids if str(x).strip()]
            media_ids.extend(new_ids)
            sent_count += len(chunk)
            if is_final_chunk:
                final_caption_message_id = str(media_result.message_id)
            self._delivery_ack(
                article_id, message_id=str(media_result.message_id or ""), message_ids=media_ids,
                media_count=len(media_ids), complete=is_final_chunk,
                mode="media_final" if is_final_chunk else "media_chunk", expected_media_count=delivery_count,
            )
            self.store.record_telegram_media_delivery(
                article_id, media_ids,
                caption_attached=is_final_chunk,
                caption_message_id=final_caption_message_id if is_final_chunk else "",
            )
            event(
                "media", "captioned local media chunk published" if is_final_chunk else "local media chunk published",
                channel_id=channel_id, article_id=article_id, source_media_count=source_media_count,
                bundle_media_count=bundle.count, prepared_media_count=delivery_count,
                published_media_count=len(media_ids), media_outcome="COMPLETE" if is_final_chunk else "PARTIAL",
                caption_attached=is_final_chunk, source_message_ids=list(bundle.source_message_ids), upload_mode="multipart_local",
            )
            pending = pending[len(chunk):]
            if heartbeat is not None:
                try:
                    heartbeat()
                except Exception:
                    pass

        if not final_caption_message_id:
            detail = f"Усі {len(media_ids)} media message IDs є, але caption message ID відсутній."
            self.store.publication_backoff(
                article_id, blocked_by=BlockedBy.MEDIA, error_code="CAPTION_STATE_MISSING", detail=detail, retry_seconds=None,
            )
            event("media", "caption state missing after media delivery", level=40, channel_id=channel_id, article_id=article_id, detail=detail)
            return "CAPTION_STATE_MISSING"

        self._mark_published(article_id, channel, message_id=final_caption_message_id, media_count=delivery_count, message_ids=media_ids[:delivery_count])
        event(
            "publish", "published local-upload media with caption", channel_id=channel_id, article_id=article_id,
            message_id=final_caption_message_id, message_ids=media_ids[:delivery_count],
            media_policy=policy, source_media_count=source_media_count, bundle_media_count=bundle.count,
            prepared_media_count=delivery_count, published_media_count=delivery_count,
            media_outcome="COMPLETE", upload_mode="multipart_local", source_url=source_url,
        )
        return "PUBLISHED"

    def publish_ready(self, channel_id: int, heartbeat: Callable[[], None] | None = None) -> int:
        channel = self.store.get_channel(channel_id)
        if channel is None:
            return 0
        try:
            self.publish_pending_facebook(channel_id, limit=4)
        except Exception as exc:
            event("facebook", "facebook retry loop isolated", level=30, channel_id=channel_id, detail=str(exc)[:800])
        count = 0
        for article in self.store.ready_articles(channel_id, limit=max(1, channel.max_posts_per_cycle * 4)):
            if count >= max(1, channel.max_posts_per_cycle):
                break
            article_id = int(article["id"])
            approved = bool(self.store.is_human_approved_unpublished(article_id))
            previous_catchup = bool(getattr(self, "_rc110_human_catchup", False))
            try:
                self._rc110_human_catchup = approved
                ok, reason = self.can_publish_now(channel_id)
                if not ok:
                    if approved:
                        event(
                            "editorial", "human-approved catch-up waiting",
                            channel_id=channel_id, article_id=article_id, reason=reason,
                        )
                    break
                try:
                    result = self.publish_one(article_id, heartbeat=heartbeat)
                except Exception as exc:
                    retry_at = self.store.publication_backoff(
                        article_id, blocked_by=BlockedBy.TELEGRAM, error_code="PUBLISH_EXCEPTION",
                        detail=str(exc), retry_seconds=300,
                    )
                    event(
                        "publish", "publication exception deferred", level=40, channel_id=channel_id,
                        article_id=article_id, next_retry_at=retry_at, detail=str(exc)[:1000],
                    )
                    continue
            finally:
                self._rc110_human_catchup = previous_catchup
            if result == "PUBLISHED":
                count += 1
            elif result in {"MIN_INTERVAL", "OUTSIDE_WINDOW"}:
                break
        return count
