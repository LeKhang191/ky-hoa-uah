"""Cloudinary. Ảnh gốc: type=private. Bản công khai: type=upload. Bản nội bộ: type=authenticated (URL có chữ ký)."""
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
import cloudinary.utils

DELIVERY_TYPE = {"public": "upload", "internal": "authenticated"}


def configure(cloudinary_url):
    """cloudinary.config() không tự đọc tham số cloudinary_url, nên tách URL cloudinary://KEY:SECRET@CLOUD ở đây."""
    parsed = urlparse(cloudinary_url)
    if parsed.scheme != "cloudinary" or not (parsed.hostname and parsed.username and parsed.password):
        raise RuntimeError("CLOUDINARY_URL phải có dạng cloudinary://API_KEY:API_SECRET@CLOUD_NAME")
    cloudinary.config(cloud_name=parsed.hostname, api_key=parsed.username, api_secret=parsed.password, secure=True)


def put(data, folder, type):
    result = cloudinary.uploader.upload(
        data, folder=folder, type=type, resource_type="image", unique_filename=True, overwrite=False
    )
    return result["public_id"]


def move(public_id, from_type, to_type):
    cloudinary.uploader.rename(public_id, public_id, type=from_type, to_type=to_type, overwrite=True)


def url(public_id, delivery_type):
    result, _ = cloudinary.utils.cloudinary_url(
        public_id, type=delivery_type, sign_url=delivery_type != "upload", secure=True, format="jpg"
    )
    return result
