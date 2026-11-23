import io
import re
import tempfile

import pgserver
import psycopg
import pytest
from PIL import Image

from app import create_app, schema_path, storage

TABLES = "audit_logs, notifications, album_photos, albums, artwork_tags, tags, artworks, activation_codes, profiles"


@pytest.fixture(scope="session")
def pg_uri():
    server = pgserver.get_server(tempfile.mkdtemp())
    uri = server.get_uri()
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(schema_path().read_text())
    yield uri
    server.cleanup()


@pytest.fixture
def uploads(monkeypatch):
    """Thay Cloudinary bằng bản ghi trong bộ nhớ. Lưu lại mọi lần put/move để kiểm chứng."""
    calls = {"put": [], "move": []}

    def put(data, folder, type):
        calls["put"].append({"data": data, "folder": folder, "type": type})
        return f"{folder}/img{len(calls['put'])}"

    def move(public_id, from_type, to_type):
        calls["move"].append((public_id, from_type, to_type))

    monkeypatch.setattr(storage, "put", put)
    monkeypatch.setattr(storage, "move", move)
    return calls


@pytest.fixture
def app(pg_uri, uploads):
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"TRUNCATE {TABLES} CASCADE")
    return create_app(
        {
            "TESTING": True,
            "DATABASE_URL": pg_uri,
            "SECRET_KEY": "test",
            "CLOUDINARY_URL": "cloudinary://key:secret@demo",
            "JOIN_FORM_URL": "https://forms.example/join",
            "WTF_CSRF_ENABLED": False,
        }
    )


@pytest.fixture
def db(pg_uri):
    with psycopg.connect(pg_uri, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        yield c


def make_admin(app, email="admin@x.vn", name="Admin"):
    result = app.test_cli_runner().invoke(args=["create-admin", "--email", email, "--name", name])
    assert result.exit_code == 0, result.output
    return re.search(r"([A-Z2-7]{4}(?:-[A-Z2-7]{4}){3})", result.output).group(1)


def activate(client, email, code, password="matkhau123"):
    return client.post(
        "/activate", data={"email": email, "code": code, "password": password, "password2": password}
    )


def login(client, email, password="matkhau123"):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture
def admin_client(app):
    client = app.test_client()
    activate(client, "admin@x.vn", make_admin(app))
    return client


def create_member(admin_client, name, email, status="active"):
    """Admin tạo thành viên, trả về mã kích hoạt lấy từ flash."""
    r = admin_client.post(
        "/admin/members/create",
        data={"full_name": name, "email": email, "status": status},
        follow_redirects=True,
    )
    return re.search(r"([A-Z2-7]{4}(?:-[A-Z2-7]{4}){3})", r.get_data(as_text=True)).group(1)


def member_client(app, admin_client, name, email, status="active"):
    code = create_member(admin_client, name, email, status)
    client = app.test_client()
    assert activate(client, email, code).status_code == 302
    return client


def jpeg_bytes(size=(3000, 2000), color=(120, 90, 60), exif_orientation=None):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def post_artwork(client, title="Phố cổ", visibility="public", tags="Hội An", data=None):
    return client.post(
        "/upload",
        data={
            "title": title,
            "visibility": visibility,
            "tags_location": tags,
            "file": (io.BytesIO(data or jpeg_bytes()), "a.jpg"),
        },
        content_type="multipart/form-data",
    )


def approve_all(admin_client, db):
    for r in db.execute("SELECT id FROM artworks WHERE status = 'pending'").fetchall():
        admin_client.post(f"/admin/review/{r['id']}", data={"decision": "approve"})
