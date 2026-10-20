"""Final exact-post photo, album and video parity before Telegram delivery.

This is source-owned evidence only. A monitoring channel may still publish a
verified text-only post, and a network error does not discard already confirmed
article media. Never re-send an article in a committed delivery state.
"""
from __future__ import annotations

import json

from .domain import BlockedBy
from .loghub import event
from .media_pipeline import build_publication_media_bundle
from .telegram_post_preflight import check_exact_telegram_media, source_media_shortfall


def enforce_source_media_parity(publisher, channel, article_id: int, article, bundle, source_url: str):
    """Return (article, bundle) or a retry code; called after delivery preflight.

    The publisher has already checked the exact delivery journal and dedupe
    state. The guard itself never transmits messages.
    """
    check = check_exact_telegram_media(source_url)
    event(
        "media", "exact Telegram source media parity preflight",
        channel_id=channel.id, article_id=article_id, outcome=check.outcome,
        photo_expected=check.expected_photos, video_expected=check.video_expected,
        source_confirmed=len(check.media), bundle_count=bundle.count,
        photo_signal=check.photo_signal, video_signal=check.video_signal,
        reason=check.reason,
    )

    stitched = len(bundle.source_message_ids) > 1
    encoded = bundle.encoded_items
    if check.media and (
        not bundle.count or len(check.media) > bundle.count
        or (not stitched and list(check.media) != encoded)
    ):
        # A stitched article may have media from an explicitly linked adjacent
        # post; retain it. A single-post article uses the exact post's media.
        patched = dict(article)
        candidates = list(dict.fromkeys(
            [*(encoded if stitched else []), *check.media]
        ))[:24]
        patched["media_json"] = json.dumps(candidates, ensure_ascii=False)
        try:
            layout = json.loads(str(patched.get("article_layout_json") or "{}"))
            if not isinstance(layout, dict):
                layout = {}
        except (ValueError, TypeError):
            layout = {}
        telegram = dict(layout.get("telegram") or {})
        telegram["media_count"] = len(candidates)
        telegram["source_media_parity"] = "exact_post_preflight_227"
        if check.video_expected:
            telegram["video_attachment_seen"] = True
            telegram["video_recovery"] = "exact_publish_preflight"
        layout["telegram"] = telegram
        patched["article_layout_json"] = json.dumps(
            layout, ensure_ascii=False, separators=(",", ":"))
        updated = build_publication_media_bundle(channel, patched)
        if updated.count:
            publisher.store.update_article(
                article_id, media_json=patched["media_json"],
                article_layout_json=patched["article_layout_json"])
            article, bundle = patched, updated
            event(
                "media", "exact Telegram source media restored",
                channel_id=channel.id, article_id=article_id,
                restored=updated.count, source_expected_photos=check.expected_photos)

    shortfall = source_media_shortfall(check, bundle.encoded_items)
    if check.outcome == "uncertain" and not bundle.count:
        shortfall = "TELEGRAM_MEDIA_PREFLIGHT_RETRY"
    if shortfall:
        publisher.store.publication_backoff(
            article_id, blocked_by=BlockedBy.MEDIA,
            error_code=shortfall,
            detail=f"{check.outcome}: {check.reason}; photos={check.expected_photos}; "
                   f"video={check.video_expected}",
            retry_seconds=1800, count_attempt=False,
        )
        event(
            "media", "Telegram source media parity withheld", level=30,
            channel_id=channel.id, article_id=article_id, code=shortfall,
            source_expected_photos=check.expected_photos,
            available_media=bundle.count,
        )
        return shortfall
    if check.outcome == "uncertain":
        event(
            "media", "Telegram parity unverified, original media retained",
            level=30, channel_id=channel.id, article_id=article_id,
            source_url=source_url, original_media_count=bundle.count)
    return article, bundle
