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


_COARSE = 128        # coarse search resolution (longest side)
# Coarse-stage gate (speed only; the final decision is always _MAX_STRUCT after
# refinement, so a loose gate cannot create a false merge). Measured: renditions
# <= 0.08 (fine line art up to ~0.27 when the grid scale is off), different
# frames of the same scene >= 0.37.
_COARSE_STRUCT = 0.33
_FRACTIONS = tuple(round(0.92 ** k, 4) for k in range(11))   # 1.0 ... 0.43, ~8% steps


class PreparedPixels:
    """Decoded working copies of one image, built once per dedupe pass."""

    __slots__ = ("image", "coarse", "hist", "_grids")

    def __init__(self, image, coarse, hist):
        self.image = image
        self.coarse = coarse
        self.hist = hist
        self._grids = {}

    def coarse_grid(self, crop_w: int, crop_h: int):
        """Coarse placements + signatures for a crop aspect, cached per image.

        In a burst/gallery every image is compared with every other one; the
        regions of this image do not depend on the other image's pixels.
        """
        key = round(crop_w / max(1, crop_h), 2)
        grid = self._grids.get(key)
        if grid is None:
            grid = []
            for x, y, cw, ch in _placements(self.coarse.width, self.coarse.height, crop_w, crop_h):
                if cw < 12 or ch < 12 or x < 0 or y < 0 or x + cw > self.coarse.width or y + ch > self.coarse.height:
                    continue
                _colour, detail, energy = _signature(self.coarse.crop((x, y, x + cw, y + ch)))
                grid.append(((x, y, cw, ch), detail, energy))   # colour is recomputed only for finalists
            self._grids[key] = grid
        return grid


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
        small_copy = image.copy()
        small_copy.thumbnail((_COARSE, _COARSE), Image.Resampling.LANCZOS)
        return PreparedPixels(image, small_copy, [v / total for v in coarse])
    except Exception:
        return None


def _mean(channel) -> float:
    """Exact mean of a single-band image computed in C (float BOX reduction)."""
    from PIL import Image
    return float(channel.convert("F").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0)))


def _signature(image):
    """(colour 48x48, detail map, detail energy) for one image region."""
    from PIL import Image, ImageChops, ImageFilter, ImageOps
    small = image.resize((_SIG, _SIG), Image.Resampling.BILINEAR)
    grey = ImageOps.grayscale(small)
    detail = ImageChops.subtract(grey, grey.filter(ImageFilter.GaussianBlur(2)), scale=1, offset=128)
    energy = _mean(ImageChops.difference(detail, Image.new("L", detail.size, 128)))
    return small, detail, energy


def _compare(a, b) -> tuple[float, float, float, float]:
    from PIL import ImageChops
    colour = max(_mean(band) for band in ImageChops.difference(a[0], b[0]).split())
    detail_diff = _mean(ImageChops.difference(a[1], b[1]))
    ea, eb = a[2], b[2]
    return colour, detail_diff / max(0.5, ea + eb), ea, eb


def _placements(width: int, height: int, crop_w: int, crop_h: int):
    for fraction in _FRACTIONS:
        cw = int(width * fraction)
        ch = int(cw * crop_h / crop_w)
        if ch > height:
            ch = int(height * fraction)
            cw = int(ch * crop_w / crop_h)
        for ix in range(7):
            for iy in range(7):
                yield int((width - cw) * ix / 6), int((height - ch) * iy / 6), cw, ch


def _search(full: PreparedPixels, crop: PreparedPixels):
    """Best placement of ``crop`` inside ``full`` (scale + offset).

    Coarse grid on 128 px copies, then local refinement on the 384 px copies
    around the coarse optimum only (2.2.3 latency budget).
    """
    def best_of(image, target, boxes):
        best = None
        for x, y, cw, ch in boxes:
            if cw < 12 or ch < 12 or x < 0 or y < 0 or x + cw > image.width or y + ch > image.height:
                continue
            colour, struct, ea, eb = _compare(_signature(image.crop((x, y, x + cw, y + ch))), target)
            score = colour + 40.0 * struct
            if best is None or score < best[0]:
                best = (score, colour, struct, ea, eb, (x, y, cw, ch))
        return best

    from PIL import ImageChops
    target_coarse = _signature(crop.coarse)
    grid = full.coarse_grid(crop.coarse.width, crop.coarse.height)
    if not grid:
        return None
    # Rank all placements by structure only (one C reduction each), then score
    # colour + structure for the few best placements.
    ranked = sorted(
        grid,
        key=lambda entry: _mean(ImageChops.difference(entry[1], target_coarse[1]))
        / max(0.5, entry[2] + target_coarse[2]),
    )[:5]
    coarse = None
    for box, _detail, _energy in ranked:
        x, y, cw, ch = box
        colour, struct, ea, eb = _compare(_signature(full.coarse.crop((x, y, x + cw, y + ch))), target_coarse)
        score = colour + 40.0 * struct
        if coarse is None or score < coarse[0]:
            coarse = (score, colour, struct, ea, eb, box)
    if coarse[1] > 2.0 * _MAX_COLOUR or coarse[2] > _COARSE_STRUCT:
        return coarse                     # clearly different: skip refinement
    scale = full.image.width / max(1, full.coarse.width)
    x, y, cw, ch = (int(round(v * scale)) for v in coarse[5])
    target = _signature(crop.image)
    ratio = crop.image.height / max(1, crop.image.width)
    best = best_of(full.image, target, [(x, y, cw, int(round(cw * ratio)))])
    for step in (8, 4, 2, 1):
        x, y, cw, ch = best[5] if best else (x, y, cw, ch)
        boxes = [
            (x + dx, y + dy, cw + ds, int(round((cw + ds) * ratio)))
            for dx in (-step, 0, step) for dy in (-step, 0, step) for ds in (-step, 0, step)
        ]
        candidate = best_of(full.image, target, boxes)
        if candidate is not None and (best is None or candidate[0] < best[0]):
            best = candidate
    return best


def same_prepared(first: PreparedPixels | None, second: PreparedPixels | None) -> bool:
    if first is None or second is None:
        return False
    try:
        overlap = sum(min(a, b) for a, b in zip(first.hist, second.hist))
        if overlap < _MIN_HIST:
            return False
        found = [r for r in (_search(first, second),) if r]
        if not found or found[0][2] > _MAX_STRUCT:
            # The other direction only matters when the first one found no match.
            found += [r for r in (_search(second, first),) if r]
        if not found:
            return False
        _score, colour, struct, ea, eb, _box = min(found, key=lambda r: r[0])
        if colour > _MAX_COLOUR:
            return False
        if max(ea, eb) < _FLAT_ENERGY:
            # A featureless match is only meaningful when both whole images are
            # featureless. An empty patch of sky found inside a photo that does have
            # a subject is not the same picture.
            whole = max(_signature(first.image)[2], _signature(second.image)[2])
            return whole < _FLAT_ENERGY and colour <= _FLAT_COLOUR
        return struct <= _MAX_STRUCT
    except Exception:
        return False


def same_cropped_image(first: bytes, second: bytes) -> bool:
    """Find high-confidence duplicates, including resized and cropped images."""
    return same_prepared(prepare_pixels(first), prepare_pixels(second))
