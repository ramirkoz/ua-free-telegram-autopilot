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
    """Build one publication media unit without making editorial decisions.

    The bundle preserves source ordering and media kind. It reads both `media_json`
    and structured layout blocks so migrated/stiched articles do not lose media just
    because one representation is empty. Telegram allows 2..10 items in one group.
    """
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


def media_required(channel: ChannelConfig) -> bool:
    return channel.policy.normalized_media_policy() == "required"


def processing_media_gate(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> tuple[bool, str]:
    """Early media gate.

    RC18 additionally quarantines pre-RC18 Telegram snapshots until a clean source
    poll has rebuilt their media with ancestry-aware filtering. This applies to all
    policies: ``preferred`` must not race startup and publish text-only merely because
    RC17's contaminated media was intentionally discarded. Once filter version 2 is
    present, normal required/preferred/optional semantics resume.
    """
    bundle = build_media_bundle(article)
    if bundle.source_kind == "telegram":
        try:
            layout=json.loads(str(_v(article, "article_layout_json", "{}") or "{}"))
            tg=layout.get("telegram") if isinstance(layout,dict) else None
            filter_version=int(tg.get("media_filter_version") or 0) if isinstance(tg,dict) else 0
        except Exception:
            filter_version=0
        if filter_version < 2:
            return False, "TELEGRAM_MEDIA_REFRESH_REQUIRED"
    if channel.mode != ChannelMode.MONITORING or not media_required(channel):
        return True, "OK"
    if bundle.count:
        return True, "OK"
    return False, "MEDIA_REQUIRED"


def media_bundle_complete(bundle: MediaBundle) -> bool:
    """Whether every media item declared/observed at ingest survived validation."""
    return bundle.source_media_count <= bundle.count
