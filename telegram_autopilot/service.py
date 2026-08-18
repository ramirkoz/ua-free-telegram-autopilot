from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .collector import collect_source, hydrate_article_page
from .database import Database, content_hash, now_iso
from .production_pipeline_rc9 import MEDIA_POST_HARD_LIMIT, POST_FORMAT_PREFIX, TEXT_POST_HARD_LIMIT, decide
from .language import looks_english, normalize_ukrainian_terminology
from .models import Channel
from .secrets_store import load_secrets
from .telegram import TelegramError, build_post_text, send_prepared_photo, send_text
from .media_pipeline import prepare_article_media


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

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="Autopilot", daemon=True)
        self._thread.start()
        self.on_event("service", "Автопілот запущено")

    def stop(self) -> None:
        self._stop.set()
        self.on_event("service", "Автопілот зупиняється")

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
                self.on_event("error", f"Цикл: {exc}")
            self._stop.wait(15)

    def _run_channel(self, channel: Channel, *, force: bool) -> None:
        now = time.monotonic()
        due = now - self._last_collect.get(channel.id, 0) >= channel.poll_interval_minutes * 60
        if force or due:
            self._collect(channel)
            self._last_collect[channel.id] = now
        self._process(channel)

    def _collect(self, channel: Channel) -> None:
        for source in self.db.list_sources(channel.id):
            if not source.enabled:
                continue
            try:
                items = collect_source(source)
                baseline = not source.initialized
                inserted = 0
                for item in reversed(items):
                    if self.db.insert_collected(source, item, baseline=baseline):
                        inserted += 1
                self.db.source_checked(source.id, initialized=True, error=None)
                self.on_event("collect", f"{channel.name}: {source.name}: +{inserted}" + (" (baseline)" if baseline else ""))
            except Exception as exc:
                self.db.source_checked(source.id, error=str(exc)[:1000])
                self.log.warning("Source %s failed: %s", source.name, exc)
                self.on_event("error", f"{source.name}: {exc}")

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
                self.db.update_article(article_id, status="processing", processing_started_at=now_iso(), last_error=None)

                # Pending rows collected by older RC9 builds can contain a page-wide
                # media bag. Refresh them once with the article-only extractor. This
                # preserves Data while preventing stale Jaguar/banner/related images.
                try:
                    layout_existing = str(row["article_layout_json"] or "")
                    layout_version = int((json.loads(layout_existing or "{}") or {}).get("version") or 0)
                except Exception:
                    layout_version = 0
                if layout_version < 4 and str(row["url"] or "").startswith(("http://", "https://")):
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
                    self.db.update_article(article_id, status="rejected", reject_reason=f"Матеріал старіший за {channel.max_age_hours} год.")
                    continue
                if not looks_english((row["title"] or "") + "\n" + (row["raw_text"] or "")):
                    self.db.update_article(article_id, status="rejected", language="not-en", reject_reason="Матеріал не визначено як англомовний.")
                    continue
                self.db.update_article(article_id, language="en")
                exact = self.db.exact_duplicate(channel.id, article_id, row["normalized_url"], row["content_hash"])
                if exact:
                    self.db.update_article(article_id, status="duplicate", duplicate_of=exact, reject_reason=f"Точний дубль #{exact}.")
                    continue

                media_urls = self.db.media_urls(row)
                prepared_media = prepare_article_media(
                    self.db.article_layout_json(row), media_urls,
                    title=str(row["title"] or ""), article_text=str(row["raw_text"] or ""),
                )
                hero = prepared_media.telegram_hero
                telegram_hard_limit = MEDIA_POST_HARD_LIMIT if hero is not None else TEXT_POST_HARD_LIMIT
                source_footer = ""
                if channel.include_source_link and str(row["url"] or "").strip():
                    source_footer = f"\n\nДжерело: {str(row['url'] or '').strip()}"
                rewrite_hard_limit = max(300, telegram_hard_limit - len(source_footer))
                format_marker = f"{POST_FORMAT_PREFIX}{telegram_hard_limit}:{rewrite_hard_limit}:"

                event_key = str(row["event_key"] or "").strip()
                current_format = event_key.startswith(format_marker)
                headline = normalize_ukrainian_terminology(str(row["headline_uk"] or "").strip()) if current_format else ""
                body = normalize_ukrainian_terminology(str(row["teaser_text"] or "").strip()) if current_format else ""
                event_summary = str(row["event_summary"] or "").strip() if current_format else ""
                ai_provider = str(row["ai_provider"] or "").strip() if current_format else ""
                ai_model = str(row["ai_model"] or "").strip() if current_format else ""

                if not (headline and body and event_summary):
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
                        continue
                    if decision.decision == "reject":
                        self.db.update_article(
                            article_id, status="rejected", reject_reason=decision.reason,
                            event_key=decision.event_key, event_summary=decision.event_summary,
                            ai_provider=decision.provider, ai_model=decision.model,
                        )
                        continue
                    headline = decision.headline_uk
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

                caption = build_post_text(
                    headline,
                    body,
                    source_url=str(row["url"] or ""),
                    include_source_link=bool(channel.include_source_link),
                    hard_limit=telegram_hard_limit,
                )

                secrets = load_secrets()
                token = secrets.channel_bot_tokens.get(str(channel.id), "") or secrets.default_telegram_bot_token
                self.db.update_article(article_id, status="telegram_writing", rewrite_text=caption)
                try:
                    if hero is not None:
                        result = send_prepared_photo(
                            token, channel.telegram_chat_id, caption,
                            filename=hero.filename, mime_type=hero.mime_type, data=hero.data,
                        )
                    else:
                        result = send_text(token, channel.telegram_chat_id, caption)
                except TelegramError as exc:
                    if exc.media_rejected:
                        self.on_event("warning", f"{channel.name}: Telegram відхилив фото, публікую цей самий пост без медіа")
                        result = send_text(token, channel.telegram_chat_id, caption)
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
                )
                posted += 1
                self.on_event(
                    "publish",
                    f"{channel.name}: опубліковано #{article_id}, Telegram {result.message_id}, медіа {result.media_count}",
                )
            except TelegramError as exc:
                if exc.outcome_unknown:
                    status = "unknown"
                    self.db.update_article(article_id, status=status, next_retry_at=None, last_error=str(exc)[:2000])
                elif exc.retryable:
                    status = self.db.schedule_retry(article_id, str(exc))
                else:
                    status = "error"
                    self.db.update_article(article_id, status=status, next_retry_at=None, last_error=str(exc)[:2000])
                self.on_event("error", f"{channel.name}: Telegram ({status}): {exc}")
            except Exception as exc:
                status = self.db.schedule_retry(article_id, str(exc))
                self.log.exception("Article %s processing failed", article_id)
                self.on_event("error", f"{channel.name}: #{article_id} ({status}): {exc}")
