from datetime import datetime, timezone
from types import SimpleNamespace
from PIL import Image
from io import BytesIO

from telegram_autopilot.v2.visual_media_dedupe import remove_visual_duplicates


def _photo():
    img = Image.new("RGB", (800, 500))
    for x in range(800):
        for y in range(500):
            img.putpixel((x, y), ((x * 3 + y) % 255, (y * 2 + x) % 255, (x + y * 4) % 255))
    f = BytesIO()
    img.save(f, format="JPEG", quality=80)
    return f.getvalue()


def test_reencoded_same_image_not_sent_three_times():
    raw = _photo()
    original = Image.open(BytesIO(raw))
    variants = [raw]
    for quality in (65, 90):
        f = BytesIO()
        original.save(f, format="JPEG", quality=quality)
        variants.append(f.getvalue())
    items = [SimpleNamespace(kind="image", data=data) for data in variants]
    unique, count = remove_visual_duplicates(items)
    assert len(unique) == 1
    assert count == 2


def test_non_image_items_not_silently_discarded():
    items = [SimpleNamespace(kind="video", data=b"same"), SimpleNamespace(kind="video", data=b"same")]
    kept, removed = remove_visual_duplicates(items)
    assert len(kept) == 2 and removed == 0
