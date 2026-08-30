from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .rc53_hardening import operator_reaction_breakdown

FEEDBACK_WINDOW_DAYS = 7
TOTAL_TIMEOUT_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 5
MESSAGE_CHUNK_SIZE = 40
MAX_MANUAL_POSTS = 60
MAX_AUTO_POSTS = 40
MAX_REACTOR_SCAN = 1200
REACTION_PAGE_SIZE = 100
AUDIENCE_TOPIC_WEIGHT = 0.35
SOURCE_AUDIENCE_WEIGHT = 0.12

_POSITIVE_EMOJI = {"👍", "🔥", "❤", "❤️", "👏", "🎉", "💯", "🤩", "😍", "🥳", "⚡", "🏆"}
_NEGATIVE_QUALITY_EMOJI = {"👎", "🤡", "🤮", "💩"}


def row_value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def row_int(row: Mapping[str, Any] | Any, key: str) -> int:
    try:
        return max(0, int(row_value(row, key, 0) or 0))
    except Exception:
        return 0


def normalize_emoji(value: Any) -> str:
    emoticon = str(getattr(value, "emoticon", "") or "")
    if not emoticon and isinstance(value, str):
        emoticon = value
    return emoticon.replace("\ufe0f", "").strip()


def reaction_count_map(message: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    box = getattr(message, "reactions", None)
    for item in (getattr(box, "results", None) or []):
        emoji = normalize_emoji(getattr(item, "reaction", None))
        if not emoji:
            continue
        count = max(0, int(getattr(item, "count", 0) or 0))
        result[emoji] = result.get(emoji, 0) + count
    return result


def operator_choices(message: Any) -> set[str]:
    _views, _forwards, _replies, likes, dislikes, fires, _other = operator_reaction_breakdown(message)
    out: set[str] = set()
    if likes:
        out.add("👍")
    if dislikes:
        out.add("👎")
    if fires:
        out.add("🔥")
    return out


def display_user(user: Any) -> str:
    name = " ".join(
        part for part in (
            str(getattr(user, "first_name", "") or "").strip(),
            str(getattr(user, "last_name", "") or "").strip(),
        ) if part
    ).strip()
    username = str(getattr(user, "username", "") or "").strip()
    if username:
        return (name + f" (@{username})").strip()
    return name or f"admin {int(getattr(user, 'id', 0) or 0)}"


@dataclass(slots=True)
class FeedbackSnapshot:
    article_id: int
    telegram_message_id: str
    published_at: str
    views: int
    forwards: int
    replies: int
    editor_admin_count: int
    editor_reacted_count: int
    editor_likes: int
    editor_dislikes: int
    editor_fires: int
    editor_other: int
    editor_coverage: str
    reactor_scan_complete: bool
    reactor_scanned: int
    audience_counts: dict[str, int]
    audience_total: int
    audience_positive: int
    audience_negative: int
    audience_fires: int
    audience_other: int
    editor_rows: list[dict[str, Any]]


def build_snapshot(
    *,
    row: Mapping[str, Any],
    message: Any,
    editor_reactions: dict[int, set[str]],
    admin_names: dict[int, str],
    admin_count: int,
    coverage: str,
    scan_complete: bool,
    scanned: int,
) -> FeedbackSnapshot:
    views = max(0, int(getattr(message, "views", 0) or 0))
    forwards = max(0, int(getattr(message, "forwards", 0) or 0))
    replies_box = getattr(message, "replies", None)
    replies = max(0, int(getattr(replies_box, "replies", 0) or 0))
    aggregate = reaction_count_map(message)

    editor_rows: list[dict[str, Any]] = []
    editor_likes = editor_dislikes = editor_fires = editor_other = 0
    editor_emoji_counts: dict[str, int] = {}
    for actor, choices in editor_reactions.items():
        if not choices:
            continue
        for emoji in choices:
            editor_emoji_counts[emoji] = editor_emoji_counts.get(emoji, 0) + 1
        editor_likes += int("👍" in choices)
        editor_dislikes += int("👎" in choices)
        editor_fires += int("🔥" in choices)
        other = {emoji: 1 for emoji in sorted(choices) if emoji not in {"👍", "👎", "🔥"}}
        editor_other += len(other)
        editor_rows.append(
            {
                "admin_peer_id": str(actor),
                "admin_name": admin_names.get(actor, f"admin {actor}"),
                "likes": int("👍" in choices),
                "dislikes": int("👎" in choices),
                "fires": int("🔥" in choices),
                "other": other,
            }
        )

    audience_counts: dict[str, int] = {}
    for emoji, total_count in aggregate.items():
        audience_counts[emoji] = max(0, int(total_count) - int(editor_emoji_counts.get(emoji, 0)))
    audience_counts = {emoji: count for emoji, count in audience_counts.items() if count > 0}
    audience_total = sum(audience_counts.values())
    audience_positive = sum(count for emoji, count in audience_counts.items() if emoji in _POSITIVE_EMOJI)
    audience_negative = sum(count for emoji, count in audience_counts.items() if emoji in _NEGATIVE_QUALITY_EMOJI)
    audience_fires = int(audience_counts.get("🔥", 0))
    audience_other = max(0, audience_total - audience_positive - audience_negative)

    return FeedbackSnapshot(
        article_id=int(row.get("article_id") or 0),
        telegram_message_id=str(row.get("telegram_message_id") or ""),
        published_at=str(row.get("published_at") or ""),
        views=views,
        forwards=forwards,
        replies=replies,
        editor_admin_count=int(admin_count),
        editor_reacted_count=len(editor_reactions),
        editor_likes=editor_likes,
        editor_dislikes=editor_dislikes,
        editor_fires=editor_fires,
        editor_other=editor_other,
        editor_coverage=coverage,
        reactor_scan_complete=scan_complete,
        reactor_scanned=scanned,
        audience_counts=audience_counts,
        audience_total=audience_total,
        audience_positive=audience_positive,
        audience_negative=audience_negative,
        audience_fires=audience_fires,
        audience_other=audience_other,
        editor_rows=editor_rows,
    )


def audience_raw_rate(row: Mapping[str, Any] | Any) -> float:
    views = row_int(row, "views")
    if views <= 0:
        return 0.0
    positive = row_int(row, "audience_positive")
    negative = row_int(row, "audience_negative")
    fires = row_int(row, "audience_fires")
    other = row_int(row, "audience_other")
    forwards = row_int(row, "forwards")
    replies = row_int(row, "replies")
    effective = positive + 0.5 * fires + 0.25 * other + 2.0 * forwards + 0.5 * replies - 1.25 * negative
    return effective / max(1.0, float(views))


def audience_performance_score(row: Mapping[str, Any] | Any, baseline: float) -> float:
    views = row_int(row, "views")
    if views <= 0:
        return 0.0
    raw = audience_raw_rate(row)
    denom = max(0.003, abs(float(baseline)))
    relative = max(-1.0, min(2.0, (raw - float(baseline)) / denom))
    confidence = min(1.0, math.sqrt(views / 100.0))
    return relative * confidence


def age_label(value: str) -> str:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if hours < 24:
            return f"{int(hours)} год"
        return f"{int(hours // 24)} д"
    except Exception:
        return "—"


def coverage_label(value: str) -> str:
    return {
        "all_admins": "всі адміни",
        "partial_reactor_scan": "частково",
        "operator_only_fallback": "лише сесія",
        "legacy_operator": "старі дані",
    }.get(str(value or ""), str(value or "—"))
