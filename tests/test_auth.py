import re
from datetime import datetime, timedelta, timezone

from tests.conftest import activate, create_member, login, make_admin, member_client


def test_activation_sets_password_logs_in_and_code_is_single_use(app):
    code = make_admin(app)
    c = app.test_client()
    r = activate(c, "ADMIN@x.vn", code.lower())  # email/mã không phân biệt hoa thường
    assert r.status_code == 302
    assert c.get("/admin/").status_code == 200

    other = app.test_client()
    assert "không hợp lệ" in activate(other, "admin@x.vn", code, "mat-khau-khac-1").get_data(as_text=True)
    assert login(other, "admin@x.vn", "mat-khau-khac-1").status_code == 200  # vẫn ở trang login
    assert login(other, "admin@x.vn").status_code == 302  # mật khẩu đầu tiên vẫn đúng


def test_code_is_stored_hashed_only(app, db):
    code = make_admin(app)
    stored = db.execute("SELECT code_hash FROM activation_codes").fetchone()["code_hash"]
    assert code.replace("-", "") not in stored and len(stored) == 64


def test_expired_and_revoked_codes_rejected(app, db):
    code = make_admin(app)
    db.execute("UPDATE activation_codes SET expires_at = %s", (datetime.now(timezone.utc) - timedelta(minutes=1),))
    assert "hết hạn" in activate(app.test_client(), "admin@x.vn", code).get_data(as_text=True)

    db.execute("UPDATE activation_codes SET expires_at = now() + interval '1 hour', revoked_at = now()")
    assert "không hợp lệ" in activate(app.test_client(), "admin@x.vn", code).get_data(as_text=True)


def test_password_rules(app):
    code = make_admin(app)
    c = app.test_client()
    assert "ít nhất 8" in activate(c, "admin@x.vn", code, "short").get_data(as_text=True)
    r = c.post("/activate", data={"email": "admin@x.vn", "code": code, "password": "matkhau123", "password2": "khac12345"})
    assert "không khớp" in r.get_data(as_text=True)


def test_wrong_password_and_unknown_email_same_message(app, admin_client):
    c = app.test_client()
    a = login(c, "admin@x.vn", "sai").get_data(as_text=True)
    b = login(c, "nobody@x.vn", "sai").get_data(as_text=True)
    assert "Sai email hoặc mật khẩu" in a and "Sai email hoặc mật khẩu" in b


def test_locked_member_cannot_login_and_live_session_dies(app, admin_client, db):
    c = member_client(app, admin_client, "Lan", "lan@x.vn")
    assert c.get("/me").status_code == 200
    pid = db.execute("SELECT id FROM profiles WHERE email='lan@x.vn'").fetchone()["id"]
    admin_client.post(f"/admin/members/{pid}/lock")
    assert c.get("/me").status_code == 302  # session cũ bị đá ra login
    assert "bị khóa" in login(app.test_client(), "lan@x.vn").get_data(as_text=True)
    admin_client.post(f"/admin/members/{pid}/lock")  # mở khóa
    assert login(app.test_client(), "lan@x.vn").status_code == 302


def test_reissue_revokes_old_code_and_lets_member_reset_password(app, admin_client, db):
    old = create_member(admin_client, "Nam", "nam@x.vn")
    pid = db.execute("SELECT id FROM profiles WHERE email='nam@x.vn'").fetchone()["id"]
    r = admin_client.post(f"/admin/members/{pid}/reissue", follow_redirects=True)
    new = re.search(r"([A-Z2-7]{4}(?:-[A-Z2-7]{4}){3})", r.get_data(as_text=True)).group(1)
    assert new != old
    assert "không hợp lệ" in activate(app.test_client(), "nam@x.vn", old).get_data(as_text=True)
    assert activate(app.test_client(), "nam@x.vn", new, "matkhaumoi99").status_code == 302


def test_revoke_unused_code(app, admin_client, db):
    code = create_member(admin_client, "Hoa", "hoa@x.vn")
    pid = db.execute("SELECT id FROM profiles WHERE email='hoa@x.vn'").fetchone()["id"]
    admin_client.post(f"/admin/members/{pid}/revoke")
    assert "không hợp lệ" in activate(app.test_client(), "hoa@x.vn", code).get_data(as_text=True)


def test_admin_area_requires_admin(app, admin_client):
    assert app.test_client().get("/admin/").status_code == 302
    m = member_client(app, admin_client, "Mai", "mai@x.vn")
    assert m.get("/admin/").status_code == 403
    assert m.post("/admin/members/create", data={"full_name": "x", "email": "x@x.vn"}).status_code == 403


def test_admin_cannot_lock_or_demote_self(app, admin_client, db):
    me = db.execute("SELECT id FROM profiles WHERE email='admin@x.vn'").fetchone()["id"]
    assert admin_client.post(f"/admin/members/{me}/lock").status_code == 400
    assert admin_client.post(f"/admin/members/{me}/role", data={"role": "member"}).status_code == 400


def test_duplicate_email_rejected_case_insensitive(app, admin_client):
    create_member(admin_client, "A", "dup@x.vn")
    r = admin_client.post("/admin/members/create", data={"full_name": "B", "email": "DUP@x.vn", "status": "active"}, follow_redirects=True)
    assert "đã có tài khoản" in r.get_data(as_text=True)
