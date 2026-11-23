import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from . import db

CODE_TTL = timedelta(hours=72)


def _normalize(code):
    return "".join(ch for ch in code.upper() if ch.isalnum())


def hash_code(code):
    return hashlib.sha256(_normalize(code).encode()).hexdigest()


def _generate():
    raw = base64.b32encode(secrets.token_bytes(10)).decode()  # 16 ký tự, 80 bit
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def issue(profile_id):
    """Thu hồi mã chưa dùng, tạo mã mới. Trả về mã gốc — chỉ hiển thị một lần, DB chỉ giữ hash."""
    db.run(
        "UPDATE activation_codes SET revoked_at = now() WHERE profile_id = %s AND used_at IS NULL AND revoked_at IS NULL",
        (profile_id,),
    )
    code = _generate()
    db.run(
        "INSERT INTO activation_codes (profile_id, code_hash, expires_at) VALUES (%s, %s, %s)",
        (profile_id, hash_code(code), datetime.now(timezone.utc) + CODE_TTL),
    )
    return code


def revoke_unused(profile_id):
    return db.run(
        "UPDATE activation_codes SET revoked_at = now() WHERE profile_id = %s AND used_at IS NULL AND revoked_at IS NULL",
        (profile_id,),
    )
