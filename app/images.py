"""Xử lý ảnh: ảnh gốc giữ nguyên bytes; bản công khai được xoay đúng EXIF, nén và đóng watermark nhẹ."""
import io

from PIL import Image, ImageDraw, ImageFont, ImageOps

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE = 1600
WATERMARK_TEXT = "UAH - KY HOA THUC CHIEN"


def _open(data):
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise ValueError("Không đọc được file ảnh.") from e
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("Chỉ nhận ảnh JPG, PNG hoặc WEBP.")
    return ImageOps.exif_transpose(img).convert("RGB")


def _to_jpeg(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


def _shrink(img):
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    return img


def _watermark(img):
    w, h = img.size
    size = max(14, w // 40)
    font = ImageFont.load_default(size=size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, top, right, bottom = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    x, y = w - (right - left) - size, h - (bottom - top) - size
    draw.text((x + 1, y + 1), WATERMARK_TEXT, font=font, fill=(0, 0, 0, 90))
    draw.text((x, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 150))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def public_artwork(data):
    return _to_jpeg(_watermark(_shrink(_open(data))))


def plain_resized(data):
    return _to_jpeg(_shrink(_open(data)))
