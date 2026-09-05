from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Channel:
    id: int
    name: str
    telegram_chat_id: str
    editorial_profile: str
    enabled: bool
    include_source_link: bool
    poll_interval_minutes: int
    min_publish_interval_minutes: int
    dedupe_window_hours: int
    max_age_hours: int
    max_posts_per_cycle: int
    created_at: str
    updated_at: str
    editorial_weights_json: str = "[]"
    content_direction: str = "en_to_uk"
    poll_immediate: bool = False
    publish_24h: bool = False
    publish_start: str = "07:00"
    publish_end: str = "00:00"
    publish_immediately: bool = False
    topic_balance_enabled: bool = True
    topic_daily_limit: int = 2
    related_spacing_posts: int = 5
    channel_mode: str = "editorial"
    media_enrichment_mode: str = "auto"
    media_first_allowed: bool = True
    media_min_text_chars: int = 500


@dataclass(slots=True)
class Source:
    id: int
    channel_id: int
    kind: str
    name: str
    url: str
    enabled: bool
    initialized: bool
    created_at: str
    last_checked_at: str | None = None
    last_error: str | None = None
    priority: int = 100


@dataclass(slots=True)
class Decision:
    decision: str
    duplicate_of: int | None
    reason: str
    event_key: str
    event_summary: str
    headline_uk: str
    telegram_teaser: str
    full_article_uk: str
    media_captions_uk: dict[str, str]
    confidence: float
    provider: str
    model: str
