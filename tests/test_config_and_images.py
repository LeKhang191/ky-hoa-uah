import io

import pytest
from PIL import Image

from app import create_app, images, storage
from tests.conftest import jpeg_bytes


def test_missing_config_fails_fast(monkeypatch):
    for key in ("SECRET_KEY", "DATABASE_URL", "CLOUDINARY_URL", "JOIN_FORM_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_csrf_enabled_by_default(pg_uri):
    app = create_app(
        {"DATABASE_URL": pg_uri, "SECRET_KEY": "t", "CLOUDINARY_URL": "cloudinary://k:s@demo", "JOIN_FORM_URL": "x"}
    )
    r = app.test_client().post("/login", data={"email": "a@b.c", "password": "x"})
    assert r.status_code == 400


def test_public_copy_is_shrunk_watermarked_and_original_untouched():
    original = jpeg_bytes((3000, 2000), color=(10, 10, 10))
    public = images.public_artwork(original)
    img = Image.open(io.BytesIO(public))
    assert max(img.size) == 1600 and len(public) < len(original)
    # vùng góc phải dưới có pixel sáng (chữ watermark) trên nền gần đen
    w, h = img.size
    corner = img.crop((w // 2, h - h // 8, w, h)).getextrema()
    assert max(c[1] for c in corner) > 60
    # vùng góc trái trên không bị đụng tới
    assert max(c[1] for c in img.crop((0, 0, 100, 100)).getextrema()) < 40


def test_exif_orientation_is_applied():
    portrait_flag = jpeg_bytes((400, 200), exif_orientation=6)
    img = Image.open(io.BytesIO(images.public_artwork(portrait_flag)))
    assert img.size == (200, 400)


def test_rejects_non_image_and_unsupported_formats():
    with pytest.raises(ValueError):
        images.public_artwork(b"not an image")
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(ValueError, match="JPG, PNG"):
        images.public_artwork(gif.getvalue())


def test_signed_url_only_for_non_public_types(app):
    assert "/s--" in storage.url("a/b", "authenticated")
    assert "/s--" not in storage.url("a/b", "upload")
    assert "/image/authenticated/" in storage.url("a/b", "authenticated")


def test_malformed_cloudinary_url_fails_fast():
    with pytest.raises(RuntimeError, match="CLOUDINARY_URL"):
        storage.configure("https://not-cloudinary")
