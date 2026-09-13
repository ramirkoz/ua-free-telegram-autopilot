from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..media import encode_media, media_identity, valid_public_media
from .domain import ChannelConfig, ChannelMode


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
    return MediaBundle(tuple(items), source_kind, source_message_ids, stitched, declared, source_count)


def build_publication_media_bundle(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> MediaBundle:
    """Apply the actual publication contract.

    EDITORIAL is a hard product invariant: zero or exactly one *relevant* media.
    MONITORING preserves the source-owned bundle, including genuine albums.

    RC19 tried to enforce editorial single-media by truncating ``media_json`` and
    layout blocks independently. When their first items differed, the publisher
    merged them back into a two-image post. RC20 selects one candidate once, at the
    publication boundary, and all downstream code receives that one-item bundle.
    """
    raw = build_media_bundle(article)
    if channel.mode != ChannelMode.EDITORIAL or not raw.items:
        return raw

    # Reuse the mature semantic/rubbish filter from the pre-V2 extractor. It rejects
    # follow/subscribe/banner/logo/avatar/recommendation chrome, validates the
    # actual image, and scores candidate metadata against the article itself.
    chosen: MediaItem | None = None
    try:
        from ..media_pipeline import prepare_article_media

        prepared = prepare_article_media(
            str(_v(article, "article_layout_json", "{}") or "{}"),
            raw.encoded_items,
            title=str(_v(article, "title", "") or ""),
            article_text=(str(_v(article, "raw_text", "") or "") + "\n" + str(_v(article, "final_text", "") or ""))[:12000],
        )
        hero = prepared.telegram_hero
        if hero is not None and hero.kind in {"image", "video"} and hero.url:
            chosen = MediaItem(hero.kind, hero.url)
    except Exception:
        # Fail closed for editorial media. A text post is preferable to a confident
        # but unrelated visual; required-media channels will be held by the gate.
        chosen = None

    if chosen is None:
        # Migrated/very simple rows may have only media_json and no structured
        # metadata to score. Preserve one conservative fallback instead of silently
        # deleting all media. Real extracted web pages normally have featured/blocks.
        try:
            layout = json.loads(str(_v(article, "article_layout_json", "{}") or "{}"))
        except Exception:
            layout = {}
        has_structured = bool(isinstance(layout, dict) and (layout.get("featured") or layout.get("featured_video") or layout.get("blocks")))
        if not has_structured and raw.items:
            low = raw.items[0].url.casefold()
            blocked = ("banner", "subscribe", "follow", "avatar", "logo", "sponsor", "affiliate", "promo")
            if not any(term in low for term in blocked):
                chosen = raw.items[0]

    items = (chosen,) if chosen is not None else ()
    return MediaBundle(
        items=items,
        source_kind=raw.source_kind,
        source_message_ids=raw.source_message_ids,
        stitched=False,
        declared_media_count=len(items),
        source_media_count=len(items),
    )


def media_required(channel: ChannelConfig) -> bool:
    return channel.policy.normalized_media_policy() == "required"


def processing_media_gate(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> tuple[bool, str]:
    raw = build_media_bundle(article)
    if raw.source_kind == "telegram":
        try:
            layout = json.loads(str(_v(article, "article_layout_json", "{}") or "{}"))
            tg = layout.get("telegram") if isinstance(layout, dict) else None
            filter_version = int(tg.get("media_filter_version") or 0) if isinstance(tg, dict) else 0
        except Exception:
            filter_version = 0
        if filter_version < 3:
            return False, "TELEGRAM_MEDIA_REFRESH_REQUIRED"
    if channel.mode != ChannelMode.MONITORING or not media_required(channel):
        return True, "OK"
    if raw.count:
        return True, "OK"
    return False, "MEDIA_REQUIRED"


def media_bundle_complete(bundle: MediaBundle) -> bool:
    return bundle.source_media_count <= bundle.count
