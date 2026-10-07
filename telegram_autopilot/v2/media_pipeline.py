from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..media import encode_media, media_identity, valid_public_media
from .domain import ChannelConfig, ChannelMode, EditorialRuntimeProfile


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


@dataclass(frozen=True, slots=True)
class MediaItem:
    kind: str
    url: str

    @property
    def encoded(self) -> str:
        return encode_media(self.kind, self.url)


@dataclass(frozen=True, slots=True)
class MediaBundle:
    items: tuple[MediaItem, ...]
    source_kind: str = ""
    source_message_ids: tuple[str, ...] = ()
    stitched: bool = False
    declared_media_count: int = 0
    source_media_count: int = 0
    video_link: str = ""
    gallery_detected: bool = False
    gallery_items_found: int = 0
    gallery_items_kept: int = 0
    video_embed_count: int = 0
    web_media_source: str = ""

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def is_group(self) -> bool:
        return len(self.items) >= 2

    @property
    def encoded_items(self) -> list[str]:
        return [item.encoded for item in self.items]


def build_media_bundle(article: Mapping[str, Any] | Any, *, max_items: int = 24) -> MediaBundle:
    """Build the raw source-owned media bundle without mode decisions."""
    try:
        raw = json.loads(str(_v(article, "media_json", "[]") or "[]"))
    except Exception:
        raw = []
    raw_values: list[str] = [str(x) for x in raw] if isinstance(raw, list) else []

    source_kind = ""
    source_message_ids: tuple[str, ...] = ()
    stitched = False
    declared = 0
    gallery_detected = False
    gallery_items_found = 0
    video_embed_count = 0
    web_media_source = ""
    try:
        layout = json.loads(str(_v(article, "article_layout_json", "{}") or "{}"))
    except Exception:
        layout = {}
    if isinstance(layout, dict):
        source_kind = str(layout.get("source_kind") or "")
        blocks = layout.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict) or str(block.get("type") or "") != "media":
                    continue
                kind = str(block.get("kind") or "image").casefold()
                url = str(block.get("url") or "").strip()
                if bool(block.get("gallery")):
                    gallery_detected = True
                    gallery_items_found += 1
                if kind == "iframe":
                    video_embed_count += 1
                if kind in {"image", "video"} and url:
                    raw_values.append(encode_media(kind, url))
        tg = layout.get("telegram")
        if isinstance(tg, dict):
            mids = tg.get("message_ids")
            if isinstance(mids, list):
                source_message_ids = tuple(str(x) for x in mids if str(x).strip())
            stitched = bool(tg.get("stitched"))
            try:
                declared = int(tg.get("media_count") or 0)
            except Exception:
                declared = 0

    items: list[MediaItem] = []
    seen: set[str] = set()
    valid_source_items = 0
    for value in raw_values:
        parsed = valid_public_media(str(value or ""))
        if not parsed:
            continue
        kind, url = parsed
        if kind not in {"image", "video"}:
            continue
        key = media_identity(kind, url)
        if key in seen:
            continue
        seen.add(key)
        valid_source_items += 1
        if len(items) < max(1, min(24, int(max_items))):
            items.append(MediaItem(kind, url))

    identity_version = 0
    if isinstance(layout, dict):
        tg_meta = layout.get("telegram")
        if isinstance(tg_meta, dict):
            try:
                identity_version = int(tg_meta.get("media_identity_version") or 0)
            except Exception:
                identity_version = 0
    if source_kind == "telegram" and identity_version < 1 and valid_source_items:
        source_count = valid_source_items
    else:
        source_count = max(int(declared or 0), valid_source_items)
        meta = layout.get("featured_meta")
        if isinstance(meta, dict):
            web_media_source = str(meta.get("provenance") or "")
    return MediaBundle(
        tuple(items), source_kind, source_message_ids, stitched, declared, source_count,
        gallery_detected=gallery_detected, gallery_items_found=gallery_items_found,
        gallery_items_kept=min(gallery_items_found, len(items)), video_embed_count=video_embed_count,
        web_media_source=web_media_source,
    )


def build_publication_media_bundle(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> MediaBundle:
    """Build the validated publication media set.

    RC112 removes the historical EDITORIAL single-media truncation. A validated
    source gallery remains a gallery, while embedded YouTube/Vimeo players remain
    reachable through canonical video links and a safe preview when available.
    """
    raw = build_media_bundle(article)
    if channel.mode != ChannelMode.EDITORIAL:
        return raw

    chosen: list[MediaItem] = []
    video_link = ""
    gallery_detected = bool(raw.gallery_detected)
    gallery_items_found = int(raw.gallery_items_found or 0)
    video_embed_count = int(raw.video_embed_count or 0)
    try:
        from ..media_pipeline import prepare_article_media
        try:
            marketing_context = EditorialRuntimeProfile(str(channel.editorial_runtime_profile)) == EditorialRuntimeProfile.COMMERCIAL_EDITORIAL
        except Exception:
            marketing_context = False
        prepared = prepare_article_media(
            str(_v(article, "article_layout_json", "{}") or "{}"),
            raw.encoded_items,
            title=str(_v(article, "title", "") or ""),
            article_text=(str(_v(article, "raw_text", "") or "") + "\n" + str(_v(article, "final_text", "") or ""))[:12000],
            marketing_context=marketing_context,
        )
        video_link = str(getattr(prepared, "video_link", "") or "")

        # Preserve source order for body/gallery media. Iframe embeds are links, not
        # uploadable Telegram media; their preview is appended separately.
        candidates = []
        featured = getattr(prepared, "featured", None)
        body = list(getattr(prepared, "body", []) or [])
        video_preview = getattr(prepared, "video_preview", None)
        if featured is not None:
            candidates.append(featured)
        candidates.extend(body)
        if video_preview is not None:
            candidates.append(video_preview)
        # Compatibility for older test/runtime adapters that expose only telegram_hero.
        if not candidates:
            hero = getattr(prepared, "telegram_hero", None)
            if hero is not None:
                candidates.append(hero)

        seen: set[str] = set()
        for item in candidates:
            if item is None or item.kind not in {"image", "video"} or not item.url:
                continue
            key = media_identity(item.kind, item.url)
            if key in seen:
                continue
            seen.add(key)
            chosen.append(MediaItem(item.kind, item.url))
            if len(chosen) >= 24:
                break
    except Exception:
        chosen = []

    return MediaBundle(
        items=tuple(chosen),
        source_kind=raw.source_kind,
        source_message_ids=raw.source_message_ids,
        stitched=False,
        declared_media_count=len(chosen),
        source_media_count=len(chosen),
        video_link=video_link,
        gallery_detected=gallery_detected,
        gallery_items_found=gallery_items_found,
        gallery_items_kept=len(chosen) if gallery_detected else 0,
        video_embed_count=video_embed_count,
        web_media_source=raw.web_media_source,
    )

def media_required(channel: ChannelConfig) -> bool:
    return channel.policy.normalized_media_policy() == "required"


def processing_media_gate(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> tuple[bool, str]:
    raw = build_media_bundle(article)
    # RC108+ product rule: media integrity is diagnostic/enrichment only. Missing,
    # stale or not-yet-hydrated media must never prevent text processing/publication.
    if channel.policy.normalized_media_policy() == "optional":
        return True, "OK"
    if raw.source_kind == "telegram":
        video_recovery = ""
        video_seen = False
        try:
            layout = json.loads(str(_v(article, "article_layout_json", "{}") or "{}"))
            tg = layout.get("telegram") if isinstance(layout, dict) else None
            filter_version = int(tg.get("media_filter_version") or 0) if isinstance(tg, dict) else 0
            if isinstance(tg, dict):
                video_recovery = str(tg.get("video_recovery") or "").strip().casefold()
                video_seen = bool(tg.get("video_attachment_seen")) or video_recovery in {
                    "direct_video", "exact_post_video", "poster_fallback", "no_video"
                }
        except Exception:
            filter_version = 0
        if filter_version < 3:
            return False, "TELEGRAM_MEDIA_REFRESH_REQUIRED"
        has_video = any(item.kind == "video" for item in raw.items)
        if video_seen and not has_video and video_recovery in {"poster_fallback", "no_video"}:
            # RC69 media-integrity invariant: if Telegram says the source item is a
            # video, a poster screenshot is not equivalent media. Hold the item and
            # retry source hydration instead of publishing the screenshot or naked text.
            return False, "TELEGRAM_VIDEO_PENDING"
    if channel.mode != ChannelMode.MONITORING or not media_required(channel):
        return True, "OK"
    if raw.count:
        return True, "OK"
    return False, "MEDIA_REQUIRED"


def media_bundle_complete(bundle: MediaBundle) -> bool:
    return bundle.source_media_count <= bundle.count
