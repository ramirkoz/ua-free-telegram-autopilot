from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChannelMode(StrEnum):
    EDITORIAL = "editorial"
    MONITORING = "monitoring"


class Stage(StrEnum):
    COLLECTED = "COLLECTED"
    EXTRACTED = "EXTRACTED"
    DEDUPED = "DEDUPED"
    SELECTED = "SELECTED"
    WRITTEN = "WRITTEN"
    QA_PASSED = "QA_PASSED"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Decision(StrEnum):
    PENDING = "PENDING"
    PUBLISH = "PUBLISH"
    REJECT = "REJECT"
    DUPLICATE = "DUPLICATE"


class BlockedBy(StrEnum):
    NONE = "NONE"
    AI = "AI"
    SOURCE = "SOURCE"
    MEDIA = "MEDIA"
    TELEGRAM = "TELEGRAM"
    CONFIG = "CONFIG"
    QUALITY = "QUALITY"


class JobState(StrEnum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    WAITING = "WAITING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class ProviderState(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    NETWORK_DOWN = "NETWORK_DOWN"
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    MODEL_UNSUPPORTED = "MODEL_UNSUPPORTED"
    CONFIG_ERROR = "CONFIG_ERROR"


@dataclass(slots=True)
class ChannelPolicy:
    channel_id: int = 0
    enabled: bool = True
    purpose: str = ""
    audience: str = "Україномовна аудиторія каналу."
    selection_rules: str = ""
    rejection_rules: str = ""
    writing_rules: str = ""
    style_rules: str = ""
    positive_examples: str = ""
    negative_examples: str = ""
    extra_instructions: str = ""
    selector_extra_prompt: str = ""
    writer_extra_prompt: str = ""
    media_policy: str = "required"
    target_min_chars: int = 300
    target_max_chars: int = 750

    def normalized_media_policy(self) -> str:
        value = str(self.media_policy or "required").strip().casefold()
        return value if value in {"required", "preferred", "optional"} else "required"


@dataclass(slots=True)
class ChannelConfig:
    id: int
    name: str
    telegram_chat_id: str
    enabled: bool = True
    mode: ChannelMode = ChannelMode.EDITORIAL
    editorial_profile: str = ""
    include_source_link: bool = True
    source_link_required: bool = True
    poll_interval_minutes: int = 5
    poll_immediate: bool = False
    min_publish_interval_minutes: int = 10
    dedupe_window_hours: int = 72
    max_age_hours: int = 24
    max_posts_per_cycle: int = 3
    publish_24h: bool = False
    publish_start: str = "07:00"
    publish_end: str = "00:00"
    publish_immediately: bool = False
    topic_balance_enabled: bool = True
    topic_daily_limit: int = 2
    related_spacing_posts: int = 5
    editorial_weights_json: str = "[]"
    language_mode: str = "ukru_to_uk"
    media_enrichment_mode: str = "auto"
    media_first_allowed: bool = True
    media_min_text_chars: int = 500
    policy: ChannelPolicy = field(default_factory=ChannelPolicy)


@dataclass(slots=True)
class ProviderHealth:
    provider: str
    state: ProviderState = ProviderState.UNKNOWN
    model: str = ""
    detail: str = ""
    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0
    cooldown_until: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class AIModelHealth:
    provider: str
    model: str
    state: ProviderState = ProviderState.UNKNOWN
    detail: str = ""
    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0
    cooldown_until: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class MigrationReport:
    source: str
    channels_total: int = 0
    channels_imported: int = 0
    sources_total: int = 0
    sources_imported: int = 0
    articles_total: int = 0
    articles_imported: int = 0
    published_imported: int = 0
    pending_reevaluation: int = 0
    archived_unpublished: int = 0
    feedback_imported: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped_runtime_state: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "channels_total": self.channels_total,
            "channels_imported": self.channels_imported,
            "sources_total": self.sources_total,
            "sources_imported": self.sources_imported,
            "articles_total": self.articles_total,
            "articles_imported": self.articles_imported,
            "published_imported": self.published_imported,
            "pending_reevaluation": self.pending_reevaluation,
            "archived_unpublished": self.archived_unpublished,
            "feedback_imported": self.feedback_imported,
            "warnings": list(self.warnings),
            "skipped_runtime_state": list(self.skipped_runtime_state),
        }
