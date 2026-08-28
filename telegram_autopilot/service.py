from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .collector import collect_source, hydrate_article_page
from .ai_router import AIRouterError
from .database import Database, content_hash, now_iso
from .event_dedupe import find_event_duplicate
from .production_pipeline import MEDIA_POST_HARD_LIMIT, POST_FORMAT_PREFIX, TEXT_POST_HARD_LIMIT, PostAIQAExhausted, decide
from .language import looks_english, normalize_ukrainian_terminology
from .models import Channel
from .secrets_store import load_secrets
from .telegram import TelegramError, build_post_text, send_prepared_photo, send_video_url
from .media_pipeline import prepare_article_media
from .language_tool_local import LanguageToolUnavailable, ensure_languagetool_async, languagetool_status


def _marketing_media_context(channel: Channel) -> bool:
    haystack = f"{channel.name} {channel.editorial_profile}".casefold()
    return any(token in haystack for token in (
        "продано", "marketing", "advertis", "реклам", "brand", "бренд", "campaign",
    ))


class AutopilotService:
    def __init__(self, db: Database, on_event=None):
        self.db = db
        self.on_event = on_event or (lambda *_: None)
        self.log = logging.getLogger("telegram_autopilot")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_collect: dict[int, float] = {}

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, kind: str, text: str) -> None:
        # UI/telemetry callbacks are observability only. They must never be able
        # to stop collection, AI processing or Telegram publication.
        try:
            self.on_event(kind, text)
        except Exception as exc:
            self.log.debug("UI event skipped (%s): %s", kind, exc)

    def _audit(self, stage: str, outcome: str, detail: str = "", **refs) -> None:
        # Observability must never become a new production failure mode.
        try:
            self.db.audit(stage, outcome, detail, **refs)
        except Exception as exc:
            self.log.debug("Audit write skipped: %s", exc)

    def _languagetool_event(self, kind: str, text: str) -> None:
        self._audit("languagetool", kind, text)
        self._emit(kind, text)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="Autopilot", daemon=True)
        self._thread.start()
        lt_ready = ensure_languagetool_async(self._languagetool_event)
        lt = languagetool_status()
        self._audit("languagetool", "ready" if lt_ready or lt.get("ready") else "starting", str(lt.get("text") or ""))
        self._emit("languagetool", str(lt.get("text") or "LanguageTool: перевірка/встановлення у фоні"))
        self._emit("service", "Автопілот запущено")

    def stop(self) -> None:
        self._stop.set()
        self._emit("service", "Автопілот зупиняється")

    def run_once(self) -> None:
        for channel in self.db.list_channels():
            if channel.enabled:
                self._run_channel(channel, force=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                for channel in self.db.list_channels():
                    if self._stop.is_set():
                        break
                    if channel.enabled:
                        self._run_channel(channel, force=False)
            except Exception as exc:
                self.log.exception("Autopilot cycle failed: %s", exc)
                self._emit("error", f"Цикл: {exc}")
            self._stop.wait(15)

    def _run_channel(self, channel: Channel, *, force: bool) -> None:
        now = time.monotonic()
        due = now - self._last_collect.get(channel.id, 0) >= channel.poll_interval_minutes * 60
        if force or due:
            self._collect(channel, force=force)
            self._last_collect[channel.id] = now
        self._process(channel)

    def _source_backoff_remaining(self, source_id: int) -> int:
        """Persist rate-limit/network backoff via the existing source_health row."""
        try:
            health = self.db.source_health(source_id)
            error = str(health.get("last_error") or "")
            stamp = str(health.get("last_error_at") or "")
            if not error or not stamp:
                return 0
            low = error.casefold()
            if "http 429" in low:
                window = 20 * 60
            elif "http 403" in low:
                window = 10 * 60
            elif "network request failed" in low or "no dns result" in low:
                window = 3 * 60
            else:
                return 0
            failed_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if failed_at.tzinfo is None:
                failed_at = failed_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - failed_at.astimezone(timezone.utc)).total_seconds()
            return max(0, int(window - age))
        except Exception:
            return 0

    def _collect(self, channel: Channel, *, force: bool = False) -> None:
        for source in self.db.list_sources(channel.id):
            if not source.enabled:
                continue
            # Do not hammer a source that just told us to slow down. The state is
            # read from source_health, so a program restart does not reset the pause.
            if not force and self._source_backoff_remaining(source.id) > 0:
                continue
            try:
                items = collect_source(source)
                baseline = not source.initialized
                inserted = 0
                for item in reversed(items):
                    if self.db.insert_collected(source, item, baseline=baseline):
                        inserted += 1
                self.db.source_checked(
                    source.id, initialized=True, error=None, inserted_count=inserted, baseline=baseline
                )
                self._audit(
                    "collect", "baseline" if baseline else "success", f"{source.name}: +{inserted}",
                    channel_id=channel.id, source_id=source.id,
                )
                self._emit("collect", f"{channel.name}: {source.name}: +{inserted}" + (" (baseline)" if baseline else ""))
            except Exception as exc:
                self.db.source_checked(source.id, error=str(exc)[:1000])
                self._audit(
                    "collect", "error", f"{source.name}: {exc}", channel_id=channel.id, source_id=source.id
                )
                self.log.warning("Source %s failed: %s", source.name, exc)
                self._emit("error", f"{source.name}: {exc}")

    def _is_too_old(self, published: str | None, hours: int) -> bool:
        if not published:
            return False
        try:
            dt = parsedate_to_datetime(published) if "," in published or "GMT" in published.upper() else datetime.fromisoformat(published.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc) < datetime.now(timezone.utc) - timedelta(hours=hours)
        except Exception:
            return False

    def _gap_ok(self, channel: Channel) -> bool:
        if channel.min_publish_interval_minutes <= 0:
            return True
        last = self.db.last_published_at(channel.id)
        if not last:
            return True
        try:
            dt = datetime.fromisoformat(last)
            return datetime.now(dt.tzinfo or timezone.utc) - dt >= timedelta(minutes=channel.min_publish_interval_minutes)
        except Exception:
            return True

    def _process(self, channel: Channel) -> None:
        # LanguageTool liveness: LanguageTool remains a preferred local proofreader,
        # but its installer/server may never become ready on a particular Windows
        # machine.  Do not turn that optional external process into a global kill
        # switch for the collector -> AI -> Telegram pipeline.  The final
        # deterministic Ukrainian blockers and Fact Guard still run before publish.
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

                # Historical rows can contain a page-wide
                # media bag. Refresh them once with the article-only extractor. This
                # preserves Data while preventing stale Jaguar/banner/related images.
                try:
                    layout_existing = str(row["article_layout_json"] or "")
                    layout_version = int((json.loads(layout_existing or "{}") or {}).get("version") or 0)
                except Exception:
                    layout_version = 0
                if layout_version < 5 and str(row["url"] or "").startswith(("http://", "https://")):
                    hydrated = hydrate_article_page(
                        str(row["url"] or ""),
                        str(row["title"] or ""),
                        str(row["raw_text"] or ""),
                        self.db.media_urls(row),
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
                    "media", "ready" if media_present else "rejected",
                    f"raw={len(media_urls)}; body={len(prepared_media.body)}; featured={bool(prepared_media.featured)}; marketing_context={marketing_media}",
                    channel_id=channel.id, article_id=article_id,
                )
                if not media_present:
                    reason = "Немає придатного фото/відео: публікація без медіа заборонена для всіх каналів."
                    self.db.update_article(article_id, status="rejected", reject_reason=reason)
                    self._audit("media", "required_missing", reason, channel_id=channel.id, article_id=article_id)
                    continue
                telegram_hard_limit = MEDIA_POST_HARD_LIMIT
                source_url = str(row["url"] or "").strip()
                source_footer = "\n\nДжерело" if source_url else ""
                video_footer = f"\n\n🎬 Відео: {video_link}" if video_link else ""
                rewrite_hard_limit = max(300, telegram_hard_limit - len(source_footer) - len(video_footer))
                format_marker = f"{POST_FORMAT_PREFIX}{telegram_hard_limit}:{rewrite_hard_limit}:"

                event_key = str(row["event_key"] or "").strip()
                current_format = event_key.startswith(format_marker)
                headline = ""
                body = normalize_ukrainian_terminology(str(row["teaser_text"] or "").strip()) if current_format else ""
                event_summary = str(row["event_summary"] or "").strip() if current_format else ""
                ai_provider = str(row["ai_provider"] or "").strip() if current_format else ""
                ai_model = str(row["ai_model"] or "").strip() if current_format else ""

                if not (body and event_summary):
                    recent = self.db.recent_published(channel.id, channel.dedupe_window_hours, limit=30)
                    decision = decide(
                        channel, row, recent, hard_limit=rewrite_hard_limit, format_marker=format_marker
                    )
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

                # Re-check semantic duplicates immediately before the
                # Telegram write, including cached/retry rewrites. A retry may
                # have been created before another source for the same event was
                # successfully published, so an older cached path could later send
                # both posts. Compare the final Ukrainian body against fresh
                # published bodies, not only source-title similarity.
                recent_for_event = self.db.recent_published(channel.id, channel.dedupe_window_hours, limit=80)
                semantic_duplicate = find_event_duplicate(str(row["title"] or ""), body, recent_for_event)
                if semantic_duplicate is not None:
                    reason = (
                        f"Семантичний дубль #{semantic_duplicate.article_id}: "
                        f"{semantic_duplicate.reason}."
                    )
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
                    publication_body,
                    source_url=source_url,
                    include_source_link=bool(source_url),
                    hard_limit=telegram_hard_limit,
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
                        raise RuntimeError("Mandatory media disappeared after the media gate")
                except TelegramError as exc:
                    if exc.media_rejected and direct_video is not None and hero is not None:
                        self._emit("warning", f"{channel.name}: Telegram відхилив відео, пробую перевірене фото")
                        result = send_prepared_photo(
                            token, channel.telegram_chat_id, caption,
                            filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,
                        )
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
                self._emit(
                    "publish",
                    f"{channel.name}: опубліковано #{article_id}, Telegram {result.message_id}, медіа {result.media_count}",
                )
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
                # A provider-availability outage is global, not article-specific.
                # Do not turn the next several fresh stories into identical retry
                # rows in the same cycle; leave them new and try again next cycle.
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
