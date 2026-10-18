"""Pixel-grounded detection of one illustration in different encodings and crops.

Conservative on purpose: source galleries with genuinely different frames must
remain multi-image. No fixed per-channel image limit is used.

2.2.3: the matcher no longer depends on the image having strong global contrast.
Renditions are found by a bidirectional aligned search (scale + offset) on a
small colour signature combined with a high-pass *detail* map. The detail map is
what separates "same photo, other crop" from "same sky, plane moved/erased":
colour alone matched both. Pillow only; no extra runtime dependency.
"""
from __future__ import annotations

from io import BytesIO

_WORK = 384          # working resolution (longest side)
_SIG = 48            # signature size used for alignment
_MAX_COLOUR = 12.0   # mean per-channel error at the best alignment
_MAX_STRUCT = 0.20   # detail-map disagreement relative to detail energy
_FLAT_ENERGY = 1.0   # below this neither image has verifiable structure
_FLAT_COLOUR = 4.0   # featureless images must be practically identical
_MIN_HIST = 0.55     # cheap prefilter: colour histogram intersection


class PreparedPixels:
    """Decoded working copy of one image, built once per dedupe pass."""

    __slots__ = ("image", "hist")

    def __init__(self, image, hist):
        self.image = image
        self.hist = hist


def prepare_pixels(data: bytes) -> PreparedPixels | None:
    try:
        from PIL import Image, ImageOps
        with Image.open(BytesIO(data)) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
        if min(image.size) < 96:
            return None
        image.thumbnail((_WORK, _WORK), Image.Resampling.LANCZOS)
        small = image.resize((64, 64), Image.Resampling.BILINEAR)
        hist = small.histogram()
        # 256 bins per channel -> 16 bins per channel, normalised.
        coarse = [sum(hist[c * 256 + b * 16:c * 256 + b * 16 + 16]) for c in range(3) for b in range(16)]
        total = float(sum(coarse)) or 1.0
        return PreparedPixels(image, [v / total for v in coarse])
    except Exception:
        return None


def _signature(image):
    from PIL import ImageChops, ImageFilter, ImageOps, Image
    small = image.resize((_SIG, _SIG), Image.Resampling.BILINEAR)
    grey = ImageOps.grayscale(small)
    detail = ImageChops.subtract(grey, grey.filter(ImageFilter.GaussianBlur(2)), scale=1, offset=128)
    return small, detail


def _energy(detail) -> float:
    from PIL import Image, ImageChops, ImageStat
    return ImageStat.Stat(ImageChops.difference(detail, Image.new("L", detail.size, 128))).mean[0]


def _compare(a, b) -> tuple[float, float, float, float]:
    from PIL import ImageChops, ImageStat
    colour = max(ImageStat.Stat(ImageChops.difference(a[0], b[0])).mean)
    detail_diff = ImageStat.Stat(ImageChops.difference(a[1], b[1])).mean[0]
    ea, eb = _energy(a[1]), _energy(b[1])
    return colour, detail_diff / max(0.5, ea + eb), ea, eb


def _search(full, crop):
    """Best placement of ``crop`` inside ``full`` (scale + offset)."""
    target = _signature(crop)
    best = None

    def consider(x: int, y: int, cw: int, ch: int) -> None:
        nonlocal best
        if cw < 24 or ch < 24 or x < 0 or y < 0 or x + cw > full.width or y + ch > full.height:
            return
        colour, struct, ea, eb = _compare(_signature(full.crop((x, y, x + cw, y + ch))), target)
        score = colour + 40.0 * struct
        if best is None or score < best[0]:
            best = (score, colour, struct, ea, eb, (x, y, cw, ch))

    for fraction in (1.0, 0.88, 0.76, 0.64, 0.54, 0.44):
        cw = int(full.width * fraction)
        ch = int(cw * crop.height / crop.width)
        if ch > full.height:
            ch = int(full.height * fraction)
            cw = int(ch * crop.width / crop.height)
        for ix in range(7):
            for iy in range(7):
                consider(int((full.width - cw) * ix / 6), int((full.height - ch) * iy / 6), cw, ch)
    if best is None:
        return None
    x, y, cw, ch = best[5]
    for step in (8, 4, 2, 1):
        for dx in (-step, 0, step):
            for dy in (-step, 0, step):
                for ds in (-step, 0, step):
                    width = cw + ds
                    consider(x + dx, y + dy, width, int(round(width * crop.height / crop.width)))
        x, y, cw, ch = best[5]
    return best


def same_prepared(first: PreparedPixels | None, second: PreparedPixels | None) -> bool:
    if first is None or second is None:
        return False
    try:
        overlap = sum(min(a, b) for a, b in zip(first.hist, second.hist))
        if overlap < _MIN_HIST:
            return False
        found = [r for r in (_search(first.image, second.image), _search(second.image, first.image)) if r]
        if not found:
            return False
        _score, colour, struct, ea, eb, _box = min(found, key=lambda r: r[0])
        if colour > _MAX_COLOUR:
            return False
        if max(ea, eb) < _FLAT_ENERGY:
            # A featureless match is only meaningful when both whole images are
            # featureless. An empty patch of sky found inside a photo that does have
            # a subject is not the same picture.
            whole = max(_energy(_signature(first.image)[1]), _energy(_signature(second.image)[1]))
            return whole < _FLAT_ENERGY and colour <= _FLAT_COLOUR
        return struct <= _MAX_STRUCT
    except Exception:
        return False


def same_cropped_image(first: bytes, second: bytes) -> bool:
    """Find high-confidence duplicates, including resized and cropped images."""
    return same_prepared(prepare_pixels(first), prepare_pixels(second))
