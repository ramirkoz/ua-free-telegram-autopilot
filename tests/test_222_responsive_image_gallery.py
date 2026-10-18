"""Real-format regression: responsive gallery variants are one image; distinct are kept."""
from io import BytesIO
from types import SimpleNamespace
from PIL import Image, ImageDraw, ImageEnhance

from telegram_autopilot.v2.visual_media_dedupe import remove_visual_duplicates


def _encode(im, fmt="JPEG", quality=82):
    b=BytesIO()
    im.save(b, format=fmt, quality=quality)
    return b.getvalue()


def _scene():
    im=Image.new("RGB", (1200, 720), "#3579b4")
    p=ImageDraw.Draw(im)
    p.polygon([(530,140),(620,220),(690,520),(460,520)],fill="#ebebeb")
    p.ellipse((170,340,225,395),fill="#fffbb0")
    p.line((200,375,260,700),fill="white",width=9)
    p.ellipse((900,360,945,408),fill="#fffbb0")
    p.line((915,390,940,700),fill="white",width=10)
    return im


def _item(data):
    return SimpleNamespace(kind="image",data=data)


def test_f22_style_three_responsive_variants_reduce_to_one():
    im=_scene()
    responsive=im.resize((600,360))
    cropped=im.crop((180,100,1020,640))
    items=[_item(_encode(im,quality=90)),
           _item(_encode(responsive,quality=62)),
           _item(_encode(cropped,quality=80))]
    remaining,count=remove_visual_duplicates(items)
    assert count==2
    assert len(remaining)==1


def test_distinct_frames_in_same_article_stay_three_images():
    im=_scene()
    one=im.copy()
    two=im.copy()
    three=im.copy()
    p=ImageDraw.Draw(two)
    p.rectangle((60,45,560,500),fill="red")
    p=ImageDraw.Draw(three)
    p.rectangle((625,60,1170,650),fill="green")
    original=[_item(_encode(x)) for x in (one,two,three)]
    kept,count=remove_visual_duplicates(original)
    assert count==0
    assert kept==original


def test_photo_crop_and_compressed_copy_do_not_change_video():
    im=_scene()
    items=[_item(_encode(im)),_item(_encode(im.resize((600,360)),quality=58)),
           SimpleNamespace(kind="video", data=b"video payload")]
    kept,count=remove_visual_duplicates(items)
    assert count==1
    assert len(kept)==2
    assert kept[1].kind=="video"
