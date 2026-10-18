from io import BytesIO

from PIL import Image, ImageDraw

from telegram_autopilot.v2.crop_dedupe import same_cropped_image


def _encoded(image):
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _artwork():
    image = Image.new("RGB", (800, 460), "#081728")
    draw = ImageDraw.Draw(image)
    for x in range(45, 755, 20):
        draw.line((x, 60, 800 - x, 420), fill=(x % 255, 175, 230), width=4)
    draw.ellipse((310, 120, 505, 390), outline="#05e3fc", width=18)
    draw.rectangle((75, 155, 215, 355), fill="#20404f")
    return image


def test_same_illustration_in_smaller_center_crop():
    whole = _artwork()
    cropped = whole.crop((120, 50, 680, 410))
    assert same_cropped_image(_encoded(whole), _encoded(cropped))


def test_distinct_articles_do_not_collapse():
    first = _artwork()
    second = Image.new("RGB", (800, 460), "#d6b658")
    draw = ImageDraw.Draw(second)
    draw.rectangle((120, 100, 630, 385), fill="#d55511")
    assert not same_cropped_image(_encoded(first), _encoded(second))
