"""Conservative final-stage visual deduplication for Telegram media uploads.

Only compare locally downloaded image pixels. Never collapse videos, never
compare text, and retain distinct photographs even if visually similar.
"""
from __future__ import annotations

from io import BytesIO
from typing import TypeVar
from .crop_dedupe import prepare_pixels, same_prepared

T = TypeVar("T")


def _fingerprint(data: bytes):
    try:
        from PIL import Image, ImageOps, ImageStat
        with Image.open(BytesIO(data)) as original:
            rgb = ImageOps.exif_transpose(original).convert("RGB")
            w, h = rgb.size
            if min(w, h) < 96:
                return None
            from PIL import ImageFilter
            # Normalize pixel compression and scaling; strong crop differences
            # are handled by a small family of center/edge-safe insets.
            hashes = []
            for crop in (0.0, 0.08, 0.16):
                cw, ch = int(w * crop), int(h * crop)
                frame = rgb.crop((cw, ch, w - cw, h - ch)).resize((9, 8))
                grey = ImageOps.grayscale(frame)
                if ImageStat.Stat(grey).stddev[0] < 12:
                    return None
                pixels = list(grey.getdata())
                value = 0
                for y in range(8):
                    for x in range(8):
                        value = (value << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
                hashes.append(value)
            # Color signature guards against unrelated compositions with a
            # similar grayscale edge pattern.
            thumb = rgb.resize((8, 8))
            colors = tuple(tuple(v // 32 for v in p) for p in thumb.getdata())
            return hashes, colors, (w, h)
    except Exception:
        return None


def _same_image(a, b) -> bool:
    if a is None or b is None:
        return False
    ha, ca, (wa, ha_dim) = a
    hb, cb, (wb, hb_dim) = b
    ratio_a, ratio_b = wa / ha_dim, wb / hb_dim
    if abs(ratio_a - ratio_b) > 0.24:
        return False
    # A strict, cross-crop dHash plus RGB color agreement.
    distance = min((x ^ y).bit_count() for x in ha for y in hb)
    color_distance = sum(sum(abs(x - y) for x, y in zip(pa, pb)) for pa, pb in zip(ca, cb))
    return (distance <= 4 and color_distance <= 125) or (distance <= 2 and color_distance <= 220) or (distance <= 3 and color_distance <= 410 and abs(ratio_a-ratio_b) <= 0.18)


def _pixel_area(data: bytes) -> int:
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as image:
            return int(image.width * image.height)
    except Exception:
        return 0


def remove_visual_duplicates(items: list[T]) -> tuple[list[T], int]:
    """Retain the highest-resolution copy at the first occurrence's position.

    2.2.3: the pixel crop/rendition check runs for every image pair. Before, it
    only ran when the earlier image had a dHash fingerprint, and low-contrast
    photos (e.g. a jet against clear sky) never get one, so their responsive
    renditions all reached Telegram.
    """
    result: list[T] = []
    entries: list[tuple[object, object, int] | None] = []   # (fingerprint, pixels, area)
    removed = 0
    for item in items:
        if getattr(item, "kind", "") != "image":
            result.append(item)
            entries.append(None)
            continue
        data = getattr(item, "data", b"")
        sig = _fingerprint(data)
        pixels = prepare_pixels(data)
        area = _pixel_area(data)
        match = next(
            (
                index for index, other in enumerate(entries)
                if other is not None and (_same_image(sig, other[0]) or same_prepared(pixels, other[1]))
            ),
            None,
        )
        if match is None:
            result.append(item)
            entries.append((sig, pixels, area))
            continue
        removed += 1
        previous = entries[match]
        if previous is not None and area > previous[2]:
            result[match] = item
            entries[match] = (sig, pixels, area)
    return result, removed
