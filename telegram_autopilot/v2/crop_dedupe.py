"""Pixel-grounded detection of one illustration in different encodings and crops.

Conservative on purpose: source galleries with genuinely different frames must
remain multi-image. No fixed per-channel image limit is used.
"""
from __future__ import annotations

from io import BytesIO


def _mean_error(a, b) -> float:
    from PIL import ImageChops, ImageStat
    diff = ImageChops.difference(a, b)
    return max(ImageStat.Stat(diff).mean)


def _normalized(image, size=(64, 64)):
    from PIL import ImageOps
    return ImageOps.fit(image, size, method=3)


def same_cropped_image(first: bytes, second: bytes) -> bool:
    """Find high-confidence duplicates, including resized and cropped images.

    Pixel comparison is sensitive to actual content, not only a dHash or URL.
    The quick equal-composition path catches responsive images with differing
    resolutions/JPEG encodings; crop search is a second conservative pass.
    """
    try:
        from PIL import Image, ImageOps
        with Image.open(BytesIO(first)) as one, Image.open(BytesIO(second)) as two:
            a = ImageOps.exif_transpose(one).convert("RGB")
            b = ImageOps.exif_transpose(two).convert("RGB")
            if min(*a.size, *b.size) < 96:
                return False
            # Same photograph resized or re-encoded. Preserve real alternate
            # photos even when subject/background looks generally similar.
            aspect_a = a.width / a.height
            aspect_b = b.width / b.height
            if abs(aspect_a - aspect_b) / max(aspect_a, aspect_b) <= 0.07:
                if _mean_error(_normalized(a), _normalized(b)) <= 20:
                    return True
            # Responsive sites serve hero plus centered / edge crops. Compare
            # only nearly identical crop pixels, not generic visual similarity.
            full, crop = sorted((a, b), key=lambda im: im.width * im.height, reverse=True)
            target = crop.resize((48, 48), resample=Image.Resampling.LANCZOS)
            for fraction in (1.0, 0.85, 0.70, 0.55, 0.40):
                cw = int(full.width * fraction)
                ch = int(cw * crop.height / crop.width)
                if ch > full.height:
                    ch = int(full.height * fraction)
                    cw = int(ch * crop.width / crop.height)
                if min(cw, ch) < 72 or cw > full.width or ch > full.height:
                    continue
                for fx in (0.0, 0.25, 0.5, 0.75, 1.0):
                    for fy in (0.0, 0.25, 0.5, 0.75, 1.0):
                        x = int((full.width - cw) * fx)
                        y = int((full.height - ch) * fy)
                        region = full.crop((x, y, x + cw, y + ch))
                        region = region.resize((48, 48), resample=Image.Resampling.LANCZOS)
                        if _mean_error(target, region) <= 13:
                            return True
    except Exception:
        return False
    return False
