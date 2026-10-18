from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw

from telegram_autopilot.v2.visual_media_dedupe import remove_visual_duplicates


def _png(image):
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _scene():
    img = Image.new("RGB", (800, 460), "#081728")
    art = ImageDraw.Draw(img)
    for x in range(45, 755, 20):
        art.line((x, 60, 800-x, 420), fill=(x % 255, 175, 230), width=4)
    art.ellipse((310, 120, 505, 390), outline="#05e3fc", width=18)
    art.rectangle((75, 155, 215, 355), fill="#20404f")
    return img


def test_publisher_deduper_removes_repeated_gallery_crop():
    original = _scene()
    duplicate = original.crop((120, 50, 680, 410))
    contrast = Image.new("RGB", (800, 460), "orange")
    ImageDraw.Draw(contrast).ellipse((200, 100, 580, 400), fill="blue")
    items = [
        SimpleNamespace(kind="image", data=_png(original)),
        SimpleNamespace(kind="image", data=_png(duplicate)),
        SimpleNamespace(kind="image", data=_png(contrast)),
    ]
    kept, removed = remove_visual_duplicates(items)
    assert removed == 1
    assert len(kept) == 2
    assert kept[0] is items[0]
    assert kept[1] is items[2]


def test_publisher_deduper_does_not_collapse_distinct_images():
    original = _scene()
    other = Image.new("RGB", original.size, "orange")
    ImageDraw.Draw(other).ellipse((200, 100, 580, 400), fill="blue")
    items = [
        SimpleNamespace(kind="image", data=_png(original)),
        SimpleNamespace(kind="image", data=_png(other)),
    ]
    kept, removed = remove_visual_duplicates(items)
    assert kept == items
    assert removed == 0
