import io

from tests.conftest import approve_all, jpeg_bytes, member_client, post_artwork


def csv_file(text, name="m.csv", bom=False):
    raw = text.encode("utf-8")
    return {"file": (io.BytesIO((b"\xef\xbb\xbf" if bom else b"") + raw), name)}


def do_import(client, text, **kw):
    return client.post("/admin/import", data=csv_file(text, **kw), content_type="multipart/form-data")


def test_import_creates_members_with_codes_that_work(app, admin_client, db):
    r = do_import(admin_client, "full_name,email,status\nNguyễn Văn A,a@x.vn,active\nTrần B,b@x.vn,former\n", bom=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Đã tạo 2 tài khoản" in html
    assert db.execute("SELECT status FROM profiles WHERE email='b@x.vn'").fetchone()["status"] == "former"
    import re
    code = re.search(r"([A-Z2-7]{4}(?:-[A-Z2-7]{4}){3})", html).group(1)
    c = app.test_client()
    first = re.search(r"<td>([^<]+)</td><td>([^<]+)</td><td><span class=\"codebox\">" + code, html)
    assert c.post("/activate", data={"email": first.group(2), "code": code, "password": "matkhau123", "password2": "matkhau123"}).status_code == 302


def test_import_is_all_or_nothing(app, admin_client, db):
    before = db.execute("SELECT count(*) AS n FROM profiles").fetchone()["n"]
    r = do_import(admin_client, "full_name,email,status\nA,a@x.vn,active\nB,khong-co-a-cong,active\nC,c@x.vn,sai\nD,a@x.vn,active\n")
    html = r.get_data(as_text=True)
    assert r.status_code == 400
    assert "Dòng 3" in html and "Dòng 4" in html and "Dòng 5" in html
    assert db.execute("SELECT count(*) AS n FROM profiles").fetchone()["n"] == before


def test_import_rejects_existing_email_missing_columns_and_empty(app, admin_client):
    assert "đã có tài khoản" in do_import(admin_client, "full_name,email\nX,admin@x.vn\n").get_data(as_text=True)
    assert "full_name và email" in do_import(admin_client, "name,mail\nX,y@z.vn\n").get_data(as_text=True)
    assert do_import(admin_client, "full_name,email\n").status_code == 400
    non_utf8 = admin_client.post("/admin/import", data={"file": (io.BytesIO("full_name,email\nĐ,d@x.vn".encode("utf-16")), "m.csv")},
                                 content_type="multipart/form-data")
    assert non_utf8.status_code == 400


def test_import_default_status_is_active(app, admin_client, db):
    do_import(admin_client, "full_name,email\nA,a@x.vn\n")
    assert db.execute("SELECT status FROM profiles WHERE email='a@x.vn'").fetchone()["status"] == "active"


def test_review_approve_reject_flow(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, title="Một")
    post_artwork(m, title="Hai")
    ids = {r["title"]: r["id"] for r in db.execute("SELECT id, title FROM artworks").fetchall()}

    no_reason = admin_client.post(f"/admin/review/{ids['Hai']}", data={"decision": "reject"}, follow_redirects=True)
    assert "Cần nhập lý do" in no_reason.get_data(as_text=True)

    admin_client.post(f"/admin/review/{ids['Một']}", data={"decision": "approve"})
    admin_client.post(f"/admin/review/{ids['Hai']}", data={"decision": "reject", "reason": "Ảnh mờ"})
    states = {r["title"]: (r["status"], r["reject_reason"]) for r in db.execute("SELECT title, status, reject_reason FROM artworks")}
    assert states == {"Một": ("approved", None), "Hai": ("rejected", "Ảnh mờ")}
    assert "Ảnh mờ" in m.get("/me").get_data(as_text=True)
    # đã quyết định thì không duyệt lại được
    assert admin_client.post(f"/admin/review/{ids['Một']}", data={"decision": "reject", "reason": "x"}).status_code == 404
    assert admin_client.post(f"/admin/review/{ids['Một']}", data={"decision": "huh"}).status_code == 400


def test_admin_review_page_can_render_internal_pending_with_signed_url(app, admin_client):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, visibility="internal")
    html = admin_client.get("/admin/review").get_data(as_text=True)
    assert "/image/authenticated/s--" in html


def test_status_and_role_changes_take_effect_and_are_audited(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    pid = db.execute("SELECT id FROM profiles WHERE email='lan@x.vn'").fetchone()["id"]
    assert m.get("/upload").status_code == 200
    admin_client.post(f"/admin/members/{pid}/status", data={"status": "break"})
    assert m.get("/upload").status_code == 403
    assert admin_client.post(f"/admin/members/{pid}/status", data={"status": "bogus"}).status_code == 400
    admin_client.post(f"/admin/members/{pid}/role", data={"role": "admin"})
    assert m.get("/admin/").status_code == 200
    actions = {r["action"] for r in db.execute("SELECT action FROM audit_logs")}
    assert {"member.status.break", "member.role.admin", "member.create", "admin.bootstrap"} <= actions
    assert "member.role.admin" in admin_client.get("/admin/logs").get_data(as_text=True)


def test_news_and_albums(app, admin_client, uploads, db):
    admin_client.post("/admin/news", data={"title": "Nghỉ sinh hoạt", "body": "Tuần này nghỉ", "type": "event"})
    assert "Nghỉ sinh hoạt" in app.test_client().get("/").get_data(as_text=True)
    assert admin_client.post("/admin/news", data={"title": "", "body": "x", "type": "news"}, follow_redirects=True) \
        and db.execute("SELECT count(*) AS n FROM notifications").fetchone()["n"] == 1

    admin_client.post("/admin/albums", data={"title": "Thực chiến 09/03", "cover": (io.BytesIO(jpeg_bytes()), "c.jpg")},
                      content_type="multipart/form-data")
    album = db.execute("SELECT * FROM albums").fetchone()
    assert uploads["put"][-1]["type"] == "upload"
    admin_client.post(f"/admin/albums/{album['id']}/photos",
                      data={"files": [(io.BytesIO(jpeg_bytes()), "1.jpg"), (io.BytesIO(jpeg_bytes()), "2.jpg")]},
                      content_type="multipart/form-data")
    assert db.execute("SELECT count(*) AS n FROM album_photos").fetchone()["n"] == 2
    page = app.test_client().get(f"/albums/{album['id']}")
    assert page.status_code == 200 and "Thực chiến 09/03" in page.get_data(as_text=True)

    n_before = len(uploads["put"])
    admin_client.post(f"/admin/albums/{album['id']}/photos",
                      data={"files": [(io.BytesIO(jpeg_bytes()), "ok.jpg"), (io.BytesIO(b"junk"), "bad.jpg")]},
                      content_type="multipart/form-data")
    assert len(uploads["put"]) == n_before  # một ảnh hỏng thì không upload ảnh nào


def test_home_shows_join_form_only_to_guests(app, admin_client):
    assert "https://forms.example/join" in app.test_client().get("/").get_data(as_text=True)
    assert "https://forms.example/join" not in admin_client.get("/").get_data(as_text=True)


def test_dashboard_counts(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m)
    html = admin_client.get("/admin/").get_data(as_text=True)
    assert "Tranh chờ duyệt: <strong>1</strong>" in html


def test_every_page_renders(app, admin_client):
    for path in ("/", "/gallery", "/login", "/activate", "/me", "/upload", "/admin/", "/admin/members", "/admin/import",
                 "/admin/review", "/admin/news", "/admin/albums", "/admin/logs"):
        assert admin_client.get(path).status_code == 200, path
    assert admin_client.get("/albums/00000000-0000-0000-0000-000000000000").status_code == 404
    assert admin_client.get("/nope").status_code == 404


def test_full_flow_with_csrf_on(pg_uri, uploads):
    import re
    from app import create_app
    app = create_app({"DATABASE_URL": pg_uri, "SECRET_KEY": "t", "CLOUDINARY_URL": "cloudinary://k:s@demo",
                      "JOIN_FORM_URL": "https://f"})
    import psycopg
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute("TRUNCATE profiles CASCADE")
    out = app.test_cli_runner().invoke(args=["create-admin", "--email", "a@x.vn", "--name", "A"]).output
    code = re.search(r"([A-Z2-7]{4}(?:-[A-Z2-7]{4}){3})", out).group(1)
    c = app.test_client()
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/activate").get_data(as_text=True)).group(1)
    r = c.post("/activate", data={"csrf_token": token, "email": "a@x.vn", "code": code, "password": "matkhau123", "password2": "matkhau123"})
    assert r.status_code == 302
    assert c.post("/admin/members/create", data={"full_name": "x", "email": "x@x.vn"}).status_code == 400  # thiếu token
