"""Evidence-based unresolved-media observations for Telegram monitoring.

Media from a neighbouring post is never silently attached. A bounded observation
can trigger operator review / later exact-post retrieval, never ownership.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Any


@dataclass(frozen=True)
class UnresolvedMedia:
    post: str
    media_count: int
    video_seen: bool
    seconds_apart: int | None
    reason: str


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


def observe_nearby_unowned_media(
    owner: Any, entries: Iterable[Any], *, window_seconds: int = 300
) -> tuple[UnresolvedMedia, ...]:
    """Record close media-only Telegram widgets, without granting ownership.

    This is deliberately NOT a stitching function. Proximity is diagnostic only.
    """
    owner_post = str(getattr(owner, "post", "") or "")
    owner_channel = owner_post.rsplit("/", 1)[0]
    owner_dt = _timestamp(getattr(owner, "published", None))
    if not owner_post or not owner_channel or owner_dt is None:
        return ()
    results = []
    for other in entries:
        post = str(getattr(other, "post", "") or "")
        if not post or post == owner_post or post.rsplit("/", 1)[0] != owner_channel:
            continue
        if str(getattr(other, "text", "") or "").strip():
            continue
        seen = bool(getattr(other, "video_attachment_seen", False))
        media = tuple(getattr(other, "media", ()) or ())
        if not seen and not media:
            continue
        other_dt = _timestamp(getattr(other, "published", None))
        if other_dt is None:
            continue
        try:
            distance = int(abs((other_dt - owner_dt).total_seconds()))
        except TypeError:
            continue
        if distance > window_seconds:
            continue
        results.append(UnresolvedMedia(
            post=post,
            media_count=len(media),
            video_seen=seen or any(str(m).startswith("video|") for m in media),
            seconds_apart=distance,
            reason="nearby_unowned_media_not_proven",
        ))
    return tuple(sorted(results, key=lambda x: (x.seconds_apart or 0, x.post)))
