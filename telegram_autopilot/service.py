from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .collector import collect_source, hydrate_article_page
from .database import Database, content_hash, now_iso
from .production_pipeline_rc9 import decide
from .language import looks_english, normalize_ukrainian_terminology, sanitize_media_caption
from .models import Channel
from .secrets_store import load_secrets, save_secrets
from .telegraph import TelegraphError, create_account, create_page
from .telegram import TelegramError, build_caption, send_prepared_photo, send_text
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

    @staticmethod
    def _author_url(channel: Channel) -> str:
        chat = channel.telegram_chat_id.strip()
        if chat.startswith("@") and len(chat) > 1:
            return "https://t.me/" + chat[1:]
        return ""

    def _telegraph_token(self) -> str:
        secrets = load_secrets()
        if secrets.telegraph_access_token:
            return secrets.telegraph_access_token
        token = create_account("ua_free_autopilot")
        secrets.telegraph_access_token = token
        save_secrets(secrets)
        self.on_event("telegraph", "Telegraph-акаунт автоматично створено та збережено")
        return token

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

                # RC7 migration-in-place: copied RC6 rows do not have structured article
                # layout. Re-fetch only pending rows so existing channels/sources/history
                # remain untouched while new Telegraph pages gain correct media order.
                try:
                    layout_existing = str(row["article_layout_json"] or "")
                except Exception:
                    layout_existing = ""
                if not layout_existing and str(row["url"] or "").startswith(("http://", "https://")):
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

                headline = normalize_ukrainian_terminology(str(row["headline_uk"] or "").strip())
                teaser = normalize_ukrainian_terminology(str(row["teaser_text"] or "").strip())
                full_article = normalize_ukrainian_terminology(str(row["full_article_uk"] or "").strip())
                event_key = str(row["event_key"] or "").strip()
                event_summary = str(row["event_summary"] or "").strip()
                ai_provider = str(row["ai_provider"] or "").strip()
                ai_model = str(row["ai_model"] or "").strip()
                media_captions = self.db.media_captions(row)

                if not (headline and teaser and full_article and event_summary):
                    recent = self.db.recent_published(channel.id, channel.dedupe_window_hours, limit=30)
                    decision = decide(channel, row, recent)
                    if decision.decision == "duplicate":
                        self.db.update_article(
                            article_id,
                            status="duplicate",
                            duplicate_of=decision.duplicate_of,
                            reject_reason=decision.reason,
                            event_key=decision.event_key,
                            event_summary=decision.event_summary,
                            ai_provider=decision.provider,
                            ai_model=decision.model,
                        )
                        continue
                    if decision.decision == "reject":
                        self.db.update_article(
                            article_id,
                            status="rejected",
                            reject_reason=decision.reason,
                            event_key=decision.event_key,
                            event_summary=decision.event_summary,
                            ai_provider=decision.provider,
                            ai_model=decision.model,
                        )
                        continue
                    headline = decision.headline_uk
                    teaser = decision.telegram_teaser
                    full_article = decision.full_article_uk
                    event_key = decision.event_key
                    event_summary = decision.event_summary
                    ai_provider = decision.provider
                    ai_model = decision.model
                    media_captions = decision.media_captions_uk
                    self.db.update_article(
                        article_id,
                        status="retry",
                        headline_uk=headline,
                        teaser_text=teaser,
                        full_article_uk=full_article,
                        event_key=event_key,
                        event_summary=event_summary,
                        ai_provider=ai_provider,
                        ai_model=ai_model,
                        media_captions_json=json.dumps({str(k): v for k, v in media_captions.items()}, ensure_ascii=False),
                    )

                media_urls = self.db.media_urls(row)
                prepared_media = prepare_article_media(
                    self.db.article_layout_json(row), media_urls,
                    title=str(row["title"] or ""), article_text=str(row["raw_text"] or ""),
                )
                # RC9 revalidates even captions stored by older Data. If the source did
                # not actually provide caption/alt metadata, a previously invented
                # caption is intentionally discarded before Telegraph publication.
                safe_captions: dict[int, str] = {}
                for media_item in prepared_media.body:
                    if media_item.index in media_captions:
                        safe = sanitize_media_caption(
                            media_captions[media_item.index], media_item.caption, media_item.alt
                        )
                        if safe:
                            safe_captions[media_item.index] = safe
                media_captions = safe_captions
                telegraph_url = str(row["telegraph_url"] or "").strip()
                if not telegraph_url:
                    # Mark the irreversible phase before the network write. A process crash here cannot cause an automatic duplicate page.
                    self.db.update_article(article_id, status="telegraph_writing")
                    page = create_page(
                        self._telegraph_token(),
                        title=headline,
                        full_text=full_article,
                        media_urls=media_urls,
                        prepared_media=prepared_media,
                        media_captions=media_captions,
                        source_url=str(row["url"] or ""),
                        author_name=channel.name,
                        author_url=self._author_url(channel),
                    )
                    telegraph_url = page.url
                    self.db.update_article(
                        article_id,
                        status="retry",
                        telegraph_url=page.url,
                        telegraph_path=page.path,
                        telegraph_created_at=now_iso(),
                    )
                    self.on_event("telegraph", f"{channel.name}: Telegraph #{article_id}, медіа {page.media_count}")

                caption = build_caption(teaser, telegraph_url)
                secrets = load_secrets()
                token = secrets.channel_bot_tokens.get(str(channel.id), "") or secrets.default_telegram_bot_token
                self.db.update_article(article_id, status="telegram_writing", rewrite_text=caption)
                try:
                    hero = prepared_media.telegram_hero
                    if hero is not None:
                        result = send_prepared_photo(
                            token, channel.telegram_chat_id, caption, filename=hero.filename,
                            mime_type=hero.mime_type, data=hero.data,
                        )
                    else:
                        result = send_text(token, channel.telegram_chat_id, caption)
                except TelegramError as exc:
                    if exc.media_rejected:
                        self.on_event("warning", f"{channel.name}: Telegram відхилив головне фото, публікую анонс без фото")
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
            except TelegraphError as exc:
                if exc.outcome_unknown:
                    status = "unknown"
                    self.db.update_article(article_id, status=status, next_retry_at=None, last_error=str(exc)[:2000])
                else:
                    status = self.db.schedule_retry(article_id, str(exc))
                self.on_event("error", f"{channel.name}: Telegraph ({status}): {exc}")
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
