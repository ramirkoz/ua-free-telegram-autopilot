from __future__ import annotations

import json
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any, Callable

from ..secrets_store import load_secrets
from ..telegram import (
    TelegramError,
    build_post_text,
    prepare_telegram_media_list,
    send_prepared_media_group,
    send_prepared_media_only,
    send_prepared_publication,
    send_text,
)
from .domain import BlockedBy
from .loghub import event
from .media_pipeline import build_media_bundle, media_bundle_complete
from .storage import V2Store
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


class Publisher:
    def __init__(self, store: V2Store):
        self.store = store

    def can_publish_now(self, channel_id: int) -> tuple[bool, str]:
        channel = self.store.get_channel(channel_id)
        if channel is None:
            return False, "CHANNEL_MISSING"
        if not channel.enabled:
            return False, "CHANNEL_DISABLED"
        if not channel.publish_24h and not _inside_window(channel.publish_start, channel.publish_end):
            return False, "OUTSIDE_WINDOW"
        if not _last_gap_ok(self.store.last_published_at(channel_id), channel.min_publish_interval_minutes):
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
        schedule_ok, schedule_reason = self.can_publish_now(channel_id)
        if not schedule_ok:
            return schedule_reason

        source_urls = _source_urls(article)
        source_url = source_urls[0] if source_urls else ""
        if not source_url.startswith(("http://", "https://")):
            self.store.block_article(article_id, blocked_by=BlockedBy.SOURCE, error_code="SOURCE_MISSING", detail="Немає canonical source URL")
            return "SOURCE_MISSING"

        text = str(article["final_text"] or "").strip()
        try:
            post_text = build_post_text(text, source_url=source_url, source_urls=source_urls, include_source_link=True, hard_limit=900)
        except TelegramError as exc:
            detail = str(exc)
            if "перевищує ліміт" in detail.casefold():
                outcome = self.store.requeue_quality_rewrite(article_id, error_code="TELEGRAM_OVERSIZE", detail=detail, max_attempts=3)
                event("publish", "oversize article removed from READY and queued for rewrite", level=30, channel_id=channel_id, article_id=article_id, chars=len(text), outcome=outcome)
                return outcome
            self.store.block_article(article_id, blocked_by=BlockedBy.QUALITY, error_code="TELEGRAM_TEXT_INVALID", detail=detail)
            return "TELEGRAM_TEXT_INVALID"

        bundle = build_media_bundle(article)
        policy = channel.policy.normalized_media_policy()
        source_media_count = int(bundle.source_media_count or bundle.declared_media_count or bundle.count)
        event(
            "media", "publication media gate", channel_id=channel_id, article_id=article_id,
            media_policy=policy, source_media_count=source_media_count,
            bundle_media_count=bundle.count, declared_media_count=bundle.declared_media_count,
            source_kind=bundle.source_kind, stitched=bundle.stitched,
        )
        if policy == "required" and not bundle.count:
            self.store.publication_backoff(article_id, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_REQUIRED", detail="Політика каналу вимагає валідне медіа", retry_seconds=None, count_attempt=False)
            event("media", "required media missing at final publication gate", level=30, channel_id=channel_id, article_id=article_id, source_media_count=source_media_count, bundle_media_count=0)
            return "MEDIA_REQUIRED"
        if policy == "required" and not media_bundle_complete(bundle):
            detail = f"Джерело має {source_media_count} медіа, але до publication bundle дійшло {bundle.count}."
            self.store.publication_backoff(article_id, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_INCOMPLETE", detail=detail, retry_seconds=None, count_attempt=False)
            event("media", "required media bundle incomplete", level=40, channel_id=channel_id, article_id=article_id, source_media_count=source_media_count, bundle_media_count=bundle.count)
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
            try:
                text_result = send_text(token, channel.telegram_chat_id, post_text, source_url=source_url, source_urls=source_urls, timeout=45.0)
            except TelegramError as exc:
                return self._telegram_failure(article_id, channel_id, exc)
            self.store.mark_published(article_id, message_id=text_result.message_id, media_count=0, message_ids=text_result.message_ids)
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
        prepared, prepare_failures = prepare_telegram_media_list(bundle.encoded_items, timeout=35.0)
        duplicate_binary_count = max(0, bundle.count - len(prepared) - len(prepare_failures))
        event(
            "media", "media prepared for telegram upload", channel_id=channel_id, article_id=article_id,
            media_policy=policy, source_media_count=source_media_count, bundle_media_count=bundle.count,
            prepared_media_count=len(prepared), failed_media_count=len(prepare_failures),
            binary_duplicates_removed=duplicate_binary_count, upload_mode="multipart_local",
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
            try:
                text_result = send_text(token, channel.telegram_chat_id, post_text, source_url=source_url, source_urls=source_urls, timeout=45.0)
            except TelegramError as exc:
                return self._telegram_failure(article_id, channel_id, exc)
            self.store.mark_published(article_id, message_id=text_result.message_id, media_count=0, message_ids=text_result.message_ids)
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
            self.store.mark_published(article_id, message_id=caption_message_id, media_count=delivery_count, message_ids=media_ids[:delivery_count])
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
            try:
                if len(chunk) == 1:
                    if is_final_chunk:
                        media_result = send_prepared_publication(
                            token, channel.telegram_chat_id, post_text, chunk[0],
                            source_url=source_url, source_urls=source_urls, timeout=75.0,
                        )
                    else:
                        media_result = send_prepared_media_only(token, channel.telegram_chat_id, chunk[0], timeout=75.0)
                else:
                    media_result = send_prepared_media_group(
                        token, channel.telegram_chat_id, chunk,
                        caption=post_text if is_final_chunk else "",
                        source_url=source_url if is_final_chunk else "",
                        source_urls=source_urls if is_final_chunk else None,
                        timeout=90.0,
                    )
            except TelegramError as exc:
                published_media_count = len(media_ids)
                event(
                    "media", "local-upload media delivery failed", level=40, channel_id=channel_id, article_id=article_id,
                    media_policy=policy, source_media_count=source_media_count, bundle_media_count=bundle.count,
                    prepared_media_count=delivery_count, published_media_count=published_media_count,
                    media_outcome="REJECTED" if exc.media_rejected else "ERROR", detail=str(exc)[:800],
                )
                if exc.media_rejected and policy in {"preferred", "optional"} and not media_ids:
                    try:
                        text_result = send_text(token, channel.telegram_chat_id, post_text, source_url=source_url, source_urls=source_urls, timeout=45.0)
                    except TelegramError as text_exc:
                        return self._telegram_failure(article_id, channel_id, text_exc)
                    self.store.mark_published(article_id, message_id=text_result.message_id, media_count=0, message_ids=text_result.message_ids)
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

        self.store.mark_published(article_id, message_id=final_caption_message_id, media_count=delivery_count, message_ids=media_ids[:delivery_count])
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
        count = 0
        for article in self.store.ready_articles(channel_id, limit=max(1, channel.max_posts_per_cycle * 4)):
            if count >= max(1, channel.max_posts_per_cycle):
                break
            ok, _ = self.can_publish_now(channel_id)
            if not ok:
                break
            article_id = int(article["id"])
            try:
                result = self.publish_one(article_id, heartbeat=heartbeat)
            except Exception as exc:
                self.store.block_article(article_id, blocked_by=BlockedBy.QUALITY, error_code="PUBLISH_EXCEPTION", detail=str(exc))
                event("publish", "publication exception isolated", level=40, channel_id=channel_id, article_id=article_id, detail=str(exc)[:1000])
                continue
            if result == "PUBLISHED":
                count += 1
            elif result in {"MIN_INTERVAL", "OUTSIDE_WINDOW"}:
                break
        return count
