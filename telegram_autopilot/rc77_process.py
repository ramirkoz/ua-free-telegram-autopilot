from __future__ import annotations

import json
import time
from typing import Any

from . import service as svc
from . import rc66_editorial_queue as rc66
from .ai_router import AIRouterError
from .collector import hydrate_article_page
from .database import content_hash, now_iso
from .event_dedupe import find_event_duplicate
from .language import normalize_ukrainian_terminology
from .language_tool_local import LanguageToolUnavailable, ensure_languagetool_async, languagetool_status
from .production_pipeline import PostAIQAExhausted
from .secrets_store import load_secrets
from .telegram import TelegramError, build_post_text


def prepare_article_media(*args: Any, **kwargs: Any):
    return svc.prepare_article_media(*args, **kwargs)

def decide(*args: Any, **kwargs: Any):
    return svc.decide(*args, **kwargs)

def looks_english(text: str) -> bool:
    return bool(svc.looks_english(text))

def _marketing_media_context(channel: Any) -> bool:
    return bool(svc._marketing_media_context(channel))

def _media_required(service: Any, channel: Any) -> bool:
    try:
        from . import rc59_universal_policy as rc59
        policy = service.db.rc59_get_channel_policy(int(channel.id))
        return str(getattr(policy, "media_policy", rc59.MEDIA_REQUIRED) or rc59.MEDIA_REQUIRED).casefold() == rc59.MEDIA_REQUIRED
    except Exception:
        return True

def send_prepared_photo(*args: Any, **kwargs: Any):
    return svc.send_prepared_photo(*args, **kwargs)

def send_video_url(*args: Any, **kwargs: Any):
    return svc.send_video_url(*args, **kwargs)

def send_text(*args: Any, **kwargs: Any):
    if bool(getattr(rc66._CONTEXT, "preparing", False)):
        return rc66._fake_result(media_count=0)
    from .telegram import send_text as real_send_text
    return real_send_text(*args, **kwargs)

MEDIA_POST_HARD_LIMIT = svc.MEDIA_POST_HARD_LIMIT
TEXT_POST_HARD_LIMIT = svc.TEXT_POST_HARD_LIMIT

def _process_rc77(self: Any, channel: Any) -> None:
    lt = languagetool_status()
    if not lt.get("ready"):
        ensure_languagetool_async(self._languagetool_event)
        note = str(lt.get("text") or "LanguageTool not ready")
        self._audit("languagetool", "degraded", note, channel_id=channel.id)
        self._emit("languagetool", note + " · автопілот продовжує роботу через вбудований UA-gate")
    posted = 0
    attempted = 0
    max_attempts = max(4, min(8, int(channel.max_posts_per_cycle) * 2))
    cycle_deadline = time.monotonic() + 180
    for row in self.db.pending_articles(channel.id, limit=30):
        if posted >= channel.max_posts_per_cycle or attempted >= max_attempts or time.monotonic() >= cycle_deadline or not self._gap_ok(channel):
            break
        attempted += 1
        article_id = int(row["id"])
        try:
            self.db.update_article(article_id, status="processing", processing_started_at=now_iso(), last_error=None, reject_reason=None)
            self._audit(
                "article", "processing", str(row["title"] or "")[:300],
                channel_id=channel.id, source_id=int(row["source_id"]), article_id=article_id,
            )

            try:
                layout_existing = str(row["article_layout_json"] or "")
                layout_version = int((json.loads(layout_existing or "{}") or {}).get("version") or 0)
            except Exception:
                layout_version = 0
            if layout_version < 5 and str(row["url"] or "").startswith(("http://", "https://")):
                hydrated = hydrate_article_page(
                    str(row["url"] or ""), str(row["title"] or ""), str(row["raw_text"] or ""), self.db.media_urls(row),
                )
                if hydrated.article_layout_json:
                    self.db.update_article(
                        article_id,
                        raw_text=hydrated.raw_text,
                        media_json=json.dumps(hydrated.media_urls[:24], ensure_ascii=False),
                        article_layout_json=hydrated.article_layout_json,
                        content_hash=content_hash(hydrated.title, hydrated.raw_text),
                        headline_uk="", teaser_text="", full_article_uk="",
                        event_key="", event_summary="", ai_provider="", ai_model="",
                        media_captions_json="{}",
                    )
                    refreshed = self.db.get_article(article_id)
                    if refreshed is not None:
                        row = refreshed

            if self._is_too_old(row["source_published_at"], channel.max_age_hours):
                reason = f"Матеріал старіший за {channel.max_age_hours} год."
                self.db.update_article(article_id, status="rejected", reject_reason=reason)
                self._audit("gate", "rejected", reason, channel_id=channel.id, article_id=article_id)
                continue
            if not looks_english((row["title"] or "") + "\n" + (row["raw_text"] or "")):
                reason = "Матеріал не визначено як англомовний."
                self.db.update_article(article_id, status="rejected", language="not-en", reject_reason=reason)
                self._audit("gate", "rejected", reason, channel_id=channel.id, article_id=article_id)
                continue
            self.db.update_article(article_id, language="en")
            exact = self.db.exact_duplicate(channel.id, article_id, row["normalized_url"], row["content_hash"])
            if exact:
                reason = f"Точний дубль #{exact}."
                self.db.update_article(article_id, status="duplicate", duplicate_of=exact, reject_reason=reason)
                self._audit("dedupe", "duplicate", reason, channel_id=channel.id, article_id=article_id)
                continue

            media_urls = self.db.media_urls(row)
            marketing_media = _marketing_media_context(channel)
            prepared_media = prepare_article_media(
                self.db.article_layout_json(row), media_urls,
                title=str(row["title"] or ""), article_text=str(row["raw_text"] or ""),
                marketing_context=marketing_media,
            )
            hero = prepared_media.telegram_hero
            direct_video = prepared_media.telegram_direct_video
            video_link = prepared_media.video_link
            media_present = hero is not None or direct_video is not None
            self._audit(
                "media", "ready" if media_present else "absent",
                f"raw={len(media_urls)}; body={len(prepared_media.body)}; featured={bool(prepared_media.featured)}; marketing_context={marketing_media}",
                channel_id=channel.id, article_id=article_id,
            )
            telegram_hard_limit = MEDIA_POST_HARD_LIMIT if media_present else TEXT_POST_HARD_LIMIT
            source_url = str(row["url"] or "").strip()
            source_footer = "\n\nДжерело" if source_url else ""
            video_footer = f"\n\n🎬 Відео: {video_link}" if video_link else ""
            rewrite_hard_limit = max(300, telegram_hard_limit - len(source_footer) - len(video_footer))
            format_marker = f"{svc.POST_FORMAT_PREFIX}{telegram_hard_limit}:{rewrite_hard_limit}:"

            event_key = str(row["event_key"] or "").strip()
            current_format = event_key.startswith(format_marker)
            headline = ""
            body = normalize_ukrainian_terminology(str(row["teaser_text"] or "").strip()) if current_format else ""
            event_summary = str(row["event_summary"] or "").strip() if current_format else ""
            ai_provider = str(row["ai_provider"] or "").strip() if current_format else ""
            ai_model = str(row["ai_model"] or "").strip() if current_format else ""

            if not (body and event_summary):
                recent = self.db.recent_published(channel.id, channel.dedupe_window_hours, limit=30)
                decision = decide(channel, row, recent, hard_limit=rewrite_hard_limit, format_marker=format_marker)
                if decision.decision == "duplicate":
                    self.db.update_article(
                        article_id, status="duplicate", duplicate_of=decision.duplicate_of,
                        reject_reason=decision.reason, event_key=decision.event_key,
                        event_summary=decision.event_summary, ai_provider=decision.provider, ai_model=decision.model,
                    )
                    self._audit("dedupe", "duplicate", decision.reason, channel_id=channel.id, article_id=article_id)
                    continue
                if decision.decision == "reject":
                    self.db.update_article(
                        article_id, status="rejected", reject_reason=decision.reason,
                        event_key=decision.event_key, event_summary=decision.event_summary,
                        ai_provider=decision.provider, ai_model=decision.model,
                    )
                    self._audit("editorial", "rejected", decision.reason, channel_id=channel.id, article_id=article_id)
                    continue
                headline = ""
                body = decision.telegram_teaser
                event_key = decision.event_key
                event_summary = decision.event_summary
                ai_provider = decision.provider
                ai_model = decision.model
                self.db.update_article(
                    article_id,
                    status="processing",
                    headline_uk=headline,
                    teaser_text=body,
                    full_article_uk=body,
                    event_key=event_key,
                    event_summary=event_summary,
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    media_captions_json="{}",
                )
                self._audit(
                    "rewrite", "pass", f"{ai_provider}/{ai_model}; chars={len(body)}; media={'video' if direct_video else ('image' if hero else 'no')}; {decision.reason[:1200]}",
                    channel_id=channel.id, article_id=article_id,
                )

            recent_for_event = self.db.recent_published(channel.id, channel.dedupe_window_hours, limit=80)
            semantic_duplicate = find_event_duplicate(str(row["title"] or ""), body, recent_for_event)
            if semantic_duplicate is not None:
                reason = f"Семантичний дубль #{semantic_duplicate.article_id}: {semantic_duplicate.reason}."
                self.db.update_article(
                    article_id,
                    status="duplicate",
                    duplicate_of=semantic_duplicate.article_id,
                    reject_reason=reason,
                    ai_provider="local-rule",
                    ai_model="event-dedupe-v2",
                )
                self._audit("dedupe", "duplicate", reason, channel_id=channel.id, article_id=article_id)
                continue

            publication_body = body + video_footer
            caption = build_post_text(
                publication_body, source_url=source_url, include_source_link=bool(source_url), hard_limit=telegram_hard_limit,
            )

            secrets = load_secrets()
            token = secrets.channel_bot_tokens.get(str(channel.id), "") or secrets.default_telegram_bot_token
            self.db.update_article(article_id, status="telegram_writing", rewrite_text=caption)
            self._audit(
                "telegram", "writing", f"chars={len(caption)}; media={'video' if direct_video else ('image' if hero else 'no')}",
                channel_id=channel.id, article_id=article_id,
            )
            try:
                if direct_video is not None:
                    result = send_video_url(token, channel.telegram_chat_id, caption, direct_video.url, source_url=source_url)
                elif hero is not None:
                    result = send_prepared_photo(
                        token, channel.telegram_chat_id, caption,
                        filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,
                    )
                else:
                    result = send_text(token, channel.telegram_chat_id, caption, source_url=source_url)
            except TelegramError as exc:
                if exc.media_rejected and direct_video is not None and hero is not None:
                    self._emit("warning", f"{channel.name}: Telegram відхилив відео, пробую перевірене фото")
                    try:
                        result = send_prepared_photo(
                            token, channel.telegram_chat_id, caption,
                            filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,
                        )
                    except TelegramError as photo_exc:
                        if photo_exc.media_rejected and not _media_required(self, channel):
                            self._emit("warning", f"{channel.name}: Telegram відхилив медіа, публікую текстом за media_policy")
                            result = send_text(token, channel.telegram_chat_id, caption, source_url=source_url)
                        else:
                            raise
                elif exc.media_rejected and not _media_required(self, channel):
                    self._emit("warning", f"{channel.name}: Telegram відхилив медіа, публікую текстом за media_policy")
                    result = send_text(token, channel.telegram_chat_id, caption, source_url=source_url)
                else:
                    raise

            self.db.update_article(
                article_id,
                status="published",
                published_at=now_iso(),
                telegram_message_id=result.message_id,
                telegram_media_count=result.media_count,
                retry_count=0,
                next_retry_at=None,
                last_error=None,
                reject_reason=None,
            )
            posted += 1
            self._audit(
                "telegram", "published", f"message_id={result.message_id}; media={result.media_count}",
                channel_id=channel.id, article_id=article_id,
            )
            self._emit("publish", f"{channel.name}: опубліковано #{article_id}, Telegram {result.message_id}, медіа {result.media_count}")
        except LanguageToolUnavailable as exc:
            status = self.db.schedule_retry(article_id, str(exc))
            self._audit("languagetool", status, str(exc), channel_id=channel.id, article_id=article_id)
            self._emit("warning", f"{channel.name}: #{article_id} ({status}): {exc}")
            break
        except PostAIQAExhausted as exc:
            status = self.db.schedule_retry(article_id, str(exc))
            self._audit("post_ai_qa", status, str(exc), channel_id=channel.id, article_id=article_id)
            self._emit("error", f"{channel.name}: #{article_id} ({status}): {exc}")
            if exc.provider_outage:
                self._audit("ai_router", "cycle_pause", "Post-AI QA exhausted because all providers are temporarily unavailable; remaining articles left new", channel_id=channel.id, article_id=article_id)
                break
        except AIRouterError as exc:
            status = self.db.schedule_retry(article_id, str(exc))
            self._audit("ai_router", status, str(exc), channel_id=channel.id, article_id=article_id)
            self._emit("error", f"{channel.name}: #{article_id} ({status}): {exc}")
            if "Немає доступного AI-провайдера" in str(exc):
                self._audit("ai_router", "cycle_pause", "No AI provider currently available; remaining articles left pending", channel_id=channel.id, article_id=article_id)
                break
        except TelegramError as exc:
            if exc.outcome_unknown:
                status = "unknown"
                self.db.update_article(article_id, status=status, next_retry_at=None, last_error=str(exc)[:2000])
            elif exc.retryable:
                status = self.db.schedule_retry(article_id, str(exc))
            else:
                status = "error"
                self.db.update_article(article_id, status=status, next_retry_at=None, last_error=str(exc)[:2000])
            self._audit("telegram", status, str(exc), channel_id=channel.id, article_id=article_id)
            self._emit("error", f"{channel.name}: Telegram ({status}): {exc}")
        except Exception as exc:
            status = self.db.schedule_retry(article_id, str(exc))
            self._audit("article", status, str(exc), channel_id=channel.id, article_id=article_id)
            self.log.exception("Article %s processing failed", article_id)
            self._emit("error", f"{channel.name}: #{article_id} ({status}): {exc}")
