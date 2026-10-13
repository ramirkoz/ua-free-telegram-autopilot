from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw

from telegram_autopilot.v2.visual_media_dedupe import remove_visual_duplicates


@dataclass
class Media:
    kind: str
    data: bytes


def picture(size=(640, 400), shifted=False):
    im = Image.new("RGB", size, (19, 42, 85))
    painter = ImageDraw.Draw(im)
    if shifted:
        painter.rectangle((0, 0, size[0] // 2, size[1]), fill=(200, 180, 27))
        painter.ellipse((120, 40, 260, 220), fill=(9, 170, 35))
    else:
        painter.polygon(((40, 20), (size[0] - 30, 70), (size[0] // 2, size[1] - 30)), fill=(220, 65, 40))
        painter.ellipse((size[0] // 4, size[1] // 3, size[0] // 2, size[1] - 50), fill=(20, 210, 150))
    out = BytesIO()
    im.save(out, "JPEG", quality=86)
    return out.getvalue()


def test_resized_same_photo_keeps_larger_original_at_first_position():
    from PIL import Image
    primary = Image.open(BytesIO(picture()))
    small = primary.resize((320, 200))
    out = BytesIO()
    small.save(out, "JPEG", quality=62)
    original = Media("image", picture())
    variant = Media("image", out.getvalue())
    kept, removed = remove_visual_duplicates([variant, original])
    assert removed == 1
    assert len(kept) == 1
    assert kept[0] is original


def test_different_gallery_photos_preserved():
    a, b = Media("image", picture()), Media("image", picture(shifted=True))
    kept, removed = remove_visual_duplicates([a, b])
    assert kept == [a, b] and removed == 0


def test_video_is_never_visually_deduplicated():
    a = Media("video", b"identical video bytes")
    kept, removed = remove_visual_duplicates([a, a])
    assert kept == [a, a] and removed == 0
