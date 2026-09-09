from __future__ import annotations

import json
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any

from ..media import decode_media, valid_public_media
from ..secrets_store import load_secrets
from ..telegram import TelegramError, build_post_text, send_publication, send_text
from .domain import BlockedBy
from .loghub import event
from .storage import V2Store


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


def _raw_media(article: Any) -> list[str]:
    try:
        items = json.loads(str(article["media_json"] or "[]"))
    except Exception:
        items = []
    result: list[str] = []
    if isinstance(items, list):
        for item in items:
            parsed = valid_public_media(str(item))
            if not parsed:
                continue
            kind, url = parsed
            if kind == "iframe":
                continue
            if url not in result:
                result.append(url)
    return result


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
        # publish_immediately means READY does not wait for a pool threshold. It never bypasses anti-spam spacing.
        if not _last_gap_ok(self.store.last_published_at(channel_id), channel.min_publish_interval_minutes):
            return False, "MIN_INTERVAL"
        return True, "OK"

    def publish_one(self, article_id: int) -> str:
        ok, reason = self.store.publication_guard(article_id)
        if not ok:
            raise ValueError(reason)
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

        source_url = str(article["canonical_source_url"] or "").strip()
        if not source_url.startswith(("http://", "https://")):
            self.store.update_article(article_id, blocked_by=str(BlockedBy.SOURCE), last_error_code="SOURCE_MISSING", last_error_detail="Немає canonical source URL")
            raise ValueError("SOURCE_MISSING")

        text = str(article["final_text"] or "").strip()
        # V2 always renders source attribution. The old include_source_link flag is kept for migration/UI history,
        # but cannot disable the mandatory publication source invariant.
        post_text = build_post_text(text, source_url=source_url, include_source_link=True, hard_limit=900)
        media = _raw_media(article)
        policy = channel.policy.normalized_media_policy()
        if policy == "required" and not media:
            self.store.update_article(article_id, blocked_by=str(BlockedBy.MEDIA), last_error_code="MEDIA_REQUIRED", last_error_detail="Політика каналу вимагає медіа")
            return "MEDIA_REQUIRED"

        secrets = load_secrets()
        token = str(secrets.channel_bot_tokens.get(str(channel_id)) or secrets.default_telegram_bot_token or "").strip()
        if not token or not channel.telegram_chat_id:
            self.store.update_article(article_id, blocked_by=str(BlockedBy.CONFIG), last_error_code="TELEGRAM_CONFIG", last_error_detail="Не налаштовано bot token/Chat ID")
            return "TELEGRAM_CONFIG"

        try:
            if media:
                try:
                    result = send_publication(token, channel.telegram_chat_id, post_text, media, source_url=source_url, timeout=55.0)
                except TelegramError as exc:
                    if exc.media_rejected and policy in {"preferred", "optional"}:
                        result = send_text(token, channel.telegram_chat_id, post_text, source_url=source_url, timeout=45.0)
                    else:
                        raise
            else:
                result = send_text(token, channel.telegram_chat_id, post_text, source_url=source_url, timeout=45.0)
        except TelegramError as exc:
            if exc.outcome_unknown:
                # Never blindly retry an unknown write outcome: duplicate posting is worse than operator review.
                self.store.update_article(article_id, blocked_by=str(BlockedBy.TELEGRAM), last_error_code="TELEGRAM_OUTCOME_UNKNOWN", last_error_detail=str(exc))
                event("publish", "telegram outcome unknown", level=40, channel_id=channel_id, article_id=article_id, detail=str(exc))
                return "TELEGRAM_OUTCOME_UNKNOWN"
            code = "TELEGRAM_RETRY" if exc.retryable else "TELEGRAM_REJECTED"
            self.store.update_article(article_id, blocked_by=str(BlockedBy.TELEGRAM), last_error_code=code, last_error_detail=str(exc))
            event("publish", "telegram publication failed", level=40, channel_id=channel_id, article_id=article_id, detail=str(exc), retryable=exc.retryable)
            return code

        self.store.mark_published(article_id, message_id=result.message_id, media_count=result.media_count)
        event("publish", "published", channel_id=channel_id, article_id=article_id, message_id=result.message_id, media_count=result.media_count, source_url=source_url)
        return "PUBLISHED"

    def publish_ready(self, channel_id: int) -> int:
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
            result = self.publish_one(int(article["id"]))
            if result == "PUBLISHED":
                count += 1
            elif result in {"MIN_INTERVAL", "OUTSIDE_WINDOW"}:
                break
        return count
