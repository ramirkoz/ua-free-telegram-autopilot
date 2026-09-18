from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import ChannelConfig, ChannelMode
from .semantic_dedupe import _concept_sequence, _value


@dataclass(frozen=True, slots=True)
class TopicMatch:
    related: bool
    shared: int = 0
    containment: float = 0.0
    title_shared: int = 0


def _topic_text(row: Any) -> str:
    return "\n".join(
        str(_value(row, key, "") or "")
        for key in ("title", "raw_text", "final_text")
    )[:10000]


def topic_match(left: Any, right: Any) -> TopicMatch:
    a = set(_concept_sequence(_topic_text(left)))
    b = set(_concept_sequence(_topic_text(right)))
    if not a or not b:
        return TopicMatch(False)
    shared = a & b
    containment = len(shared) / max(1, min(len(a), len(b)))
    ta = set(_concept_sequence(str(_value(left, "title", "") or "")))
    tb = set(_concept_sequence(str(_value(right, "title", "") or "")))
    title_shared = len(ta & tb)

    # Deliberately looser than event dedupe: this is not saying "same event". It is
    # the editorial anti-fatigue lane used to stop a monitoring feed from publishing
    # the same public-service topic from several municipalities in a row.
    related = (
        (len(shared) >= 9 and containment >= 0.34 and title_shared >= 2)
        or (len(shared) >= 12 and containment >= 0.42)
        or (title_shared >= 4 and len(shared) >= 7 and containment >= 0.30)
    )
    return TopicMatch(related, len(shared), containment, title_shared)


def topic_saturation_reason(store: Any, channel: ChannelConfig, article: Any) -> str:
    # RC54 enables anti-fatigue only for monitoring feeds. Editorial channels use
    # event dedupe but may legitimately publish several different stories in one topic.
    if channel.mode != ChannelMode.MONITORING or not bool(channel.topic_balance_enabled):
        return ""
    daily_limit = max(1, int(channel.topic_daily_limit or 1))
    spacing = max(0, int(channel.related_spacing_posts or 0))
    with store.connect() as con:
        rows = con.execute(
            """SELECT a.*,s.name AS source_name
               FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.id<>? AND a.stage='PUBLISHED'
                 AND datetime(CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END)>=datetime('now','-24 hours')
               ORDER BY datetime(CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END) DESC,a.id DESC
               LIMIT 120""",
            (int(channel.id), int(_value(article, "id", 0) or 0)),
        ).fetchall()

    related: list[tuple[Any, TopicMatch, int]] = []
    for index, row in enumerate(rows):
        match = topic_match(article, row)
        if match.related:
            related.append((row, match, index))

    if not related:
        return ""

    # Prevent bursts even when the configured daily limit is >1: related_spacing_posts
    # finally becomes an enforced setting instead of dead configuration.
    row, match, index = related[0]
    if spacing > 0 and index < spacing:
        return (
            f"TOPIC_SATURATION_SPACING: related published article #{int(row['id'])} is only "
            f"{index} posts back; required spacing={spacing}; shared={match.shared}; "
            f"containment={match.containment:.2f}; title={match.title_shared}"
        )

    if len(related) >= daily_limit:
        row, match, _ = related[daily_limit - 1]
        return (
            f"TOPIC_SATURATION_DAILY: already {len(related)} related posts in 24h "
            f"(limit={daily_limit}); example=#{int(row['id'])}; shared={match.shared}; "
            f"containment={match.containment:.2f}; title={match.title_shared}"
        )
    return ""


__all__ = ["TopicMatch", "topic_match", "topic_saturation_reason"]
