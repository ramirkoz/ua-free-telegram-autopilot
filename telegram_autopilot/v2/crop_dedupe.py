"""Conservative second-pass crop verification for a single media bundle."""
from io import BytesIO


def same_cropped_image(first: bytes, second: bytes) -> bool:
    try:
        from PIL import Image, ImageOps, ImageChops, ImageStat
        with Image.open(BytesIO(first)) as one, Image.open(BytesIO(second)) as two:
            a = ImageOps.exif_transpose(one).convert("RGB")
            b = ImageOps.exif_transpose(two).convert("RGB")
            if min(*a.size, *b.size) < 120:
                return False
            full, crop = sorted((a, b), key=lambda image: image.width * image.height, reverse=True)
            reference = crop.resize((32, 32))
            for factor in (1.0, 0.85, 0.70, 0.55, 0.40):
                cw = int(full.width * factor)
                ch = int(cw * crop.height / crop.width)
                if ch > full.height:
                    ch = int(full.height * factor)
                    cw = int(ch * crop.width / crop.height)
                if min(cw, ch) < 96 or cw > full.width or ch > full.height:
                    continue
                for px in (0.0, 0.25, 0.5, 0.75, 1.0):
                    for py in (0.0, 0.5, 1.0):
                        x = int((full.width - cw) * px)
                        y = int((full.height - ch) * py)
                        region = full.crop((x, y, x + cw, y + ch)).resize((32, 32))
                        difference = ImageStat.Stat(ImageChops.difference(reference, region))
                        if max(difference.mean) <= 12:
                            return True
    except Exception:
        return False
    return False
