"""Final exact-post photo, album and video parity before Telegram delivery.

This is source-owned evidence only. A monitoring channel may still publish a
verified text-only post, and a network error does not discard already confirmed
article media. Never re-send an article in a committed delivery state.
"""
from __future__ import annotations

import json
import re

from .domain import BlockedBy
from .loghub import event
from .media_pipeline import build_publication_media_bundle
from .telegram_post_preflight import check_exact_telegram_media, source_media_shortfall


def _verified_split_media(article: dict, bundle, source_url: str, channel) -> bool:
    """Allow only source-verified cross-post media in monitoring.
    
    A source message record is insufficient alone; every extra post must have
    explicit ownership via reply/album or a nearby photo/video link.
    """
    from .domain import ChannelMode
    if getattr(channel, "mode", None) != ChannelMode.MONITORING:
        return False
    match = re.fullmatch(r"https?://t\.me/([A-Za-z0-9_]+)/(\d+)(?:[?#].*)?", str(source_url or ""))
    if not match:
        return False
    try:
        # V2Store.get_article returns sqlite3.Row (Mapping-like without .get).
        # The LIVE 83163 crash happened after successful exact-post preflight.
        # Access the same key through [] for both sqlite3.Row and dict.
        layout = json.loads(str(article["article_layout_json"] or "{}"))
        tg = layout.get("telegram") if isinstance(layout, dict) else None
        records = tg.get("source_message_records_v1") if isinstance(tg, dict) else None
    except (ValueError, TypeError):
        return False
    if not isinstance(records, list) or len(records) < 2 or not bundle.count:
        return False
    owner_post = f"{match.group(1)}/{match.group(2)}"
    owner = next((r for r in records if isinstance(r, dict) and r.get("post") == owner_post), None)
    if not owner or not str(owner.get("text") or "").strip():
        return False
    from .strict_ingest import _explicit_same_channel_media_links
    references = _explicit_same_channel_media_links(match.group(1), str(owner.get("text") or ""))
    available: set[str] = set()
    found_linked = False
    for record in records:
        if not isinstance(record, dict):
            return False
        post = str(record.get("post") or "")
        media = record.get("media")
        if not isinstance(media, list):
            return False
        if post != owner_post:
            bound = (
                str(record.get("reply_to_post") or "") == owner_post
                or str(owner.get("reply_to_post") or "") == post
                or (bool(record.get("grouped_id"))
                    and str(record.get("grouped_id")) == str(owner.get("grouped_id") or ""))
                or post in references
            )
            if not bound:
                return False
            found_linked = found_linked or bool(media)
        available.update(str(item) for item in media if isinstance(item, str))
    return found_linked and set(bundle.encoded_items).issubset(available)


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

    # A bundle containing an extra neighbour's video/photo is not made valid
    # merely by marking itself stitched. Exact primary-post media MUST appear;
    # additional items require separately verified ownership (not available here).
    if (check.outcome in {"confirmed", "video_recovered"} and check.media
            and bundle.count > len(check.media)
            and not _verified_split_media(article, bundle, source_url, channel)):
        # 2.2.27: the exact Telegram post is now a POSITIVE independent source
        # of media truth. Earlier versions blocked forever on contaminated
        # stitched galleries even when all correct images were available.
        # Repair by keeping ONLY verified exact-post media and removing
        # unverified media blocks; never publish a neighbouring attachment.
        try:
            patched = dict(article)
            layout = json.loads(str(patched.get("article_layout_json") or "{}"))
            if not isinstance(layout, dict):
                layout = {}
            exact_media = list(dict.fromkeys(check.media))[:24]
            exact = set(exact_media)
            blocks = layout.get("blocks")
            if isinstance(blocks, list):
                from ..media import encode_media
                layout["blocks"] = [
                    b for b in blocks
                    if not isinstance(b, dict)
                    or str(b.get("type") or "") != "media"
                    or encode_media(str(b.get("kind") or "image"), str(b.get("url") or "")) in exact
                ]
            tg = dict(layout.get("telegram") or {})
            tg["media_count"] = len(exact_media)
            tg["source_media_parity"] = "exact_post_repair_2227"
            layout["telegram"] = tg
            patched["media_json"] = json.dumps(exact_media, ensure_ascii=False)
            patched["article_layout_json"] = json.dumps(layout, ensure_ascii=False)
            repaired = build_publication_media_bundle(channel, patched)
            if (repaired.count == len(exact_media)
                    and set(repaired.encoded_items) == exact
                    and not source_media_shortfall(check, repaired.encoded_items)):
                publisher.store.update_article(
                    article_id, media_json=patched["media_json"],
                    article_layout_json=patched["article_layout_json"],
                )
                article, bundle = patched, repaired
                event(
                    "media", "exact Telegram contaminated gallery safely repaired",
                    channel_id=channel.id, article_id=article_id,
                    exact_media=len(exact_media), removed_neighbour_media=True,
                )
        except Exception as exc:
            event(
                "media", "exact Telegram media repair unsafe; staying blocked",
                level=30, channel_id=channel.id, article_id=article_id,
                error=type(exc).__name__,
            )
        if bundle.count > len(check.media):
            reason = "MEDIA_CROSS_POST_CONTAMINATION"
            publisher.store.publication_backoff(
                article_id, blocked_by=BlockedBy.MEDIA, error_code=reason,
                detail=f"exact={len(check.media)} bundle={bundle.count}",
                retry_seconds=1800, count_attempt=False,
            )
            event("media", "cross-post media mismatch blocked", level=30,
                  channel_id=channel.id, article_id=article_id, code=reason)
            return reason
    stitched = len(bundle.source_message_ids) > 1
    encoded = bundle.encoded_items
    if check.media and (
        not bundle.count or len(check.media) > bundle.count
        or (not stitched and len(check.media) == bundle.count and list(check.media) != encoded)
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
