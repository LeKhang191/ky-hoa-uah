import io
import re
from html import unescape

import pytest

from tests.conftest import approve_all, jpeg_bytes, member_client, post_artwork


def seed_gallery(db, count):
    author = db.execute("INSERT INTO profiles (full_name, email) VALUES ('Họa sĩ', 'feed@x.vn') RETURNING id").fetchone()
    db.execute(
        """INSERT INTO artworks (id, author_id, title, original_id, public_id, status, created_at)
           SELECT lpad(to_hex(n), 32, '0')::uuid, %s, 'Tranh ' || n, 'original/' || n, 'public/' || n,
                  'approved', '2026-01-01T12:00:00Z'
           FROM generate_series(1, %s) AS n""",
        (author["id"], count),
    )


def next_gallery_url(html):
    link = re.search(r'rel="next" href="([^"]+)"', html)
    return unescape(link[1]) if link else None


def gallery_numbers(html):
    return [int(number) for number in re.findall(r"<h3>Tranh (\d+)", html)]


def test_gallery_paginates_with_tied_timestamps_and_new_uploads(app, db):
    seed_gallery(db, 65)
    guest = app.test_client()
    first = guest.get("/gallery")
    assert first.status_code == 200
    assert first.cache_control.private and first.cache_control.no_store
    first_html = first.get_data(as_text=True)
    assert gallery_numbers(first_html) == list(range(65, 41, -1))

    # Một tranh mới xuất hiện sau khi khách mở trang đầu.
    db.execute(
        """INSERT INTO artworks (author_id, title, original_id, public_id, status, created_at)
           SELECT id, 'Tranh 66', 'original/66', 'public/66', 'approved', '2026-01-02T12:00:00Z'
           FROM profiles WHERE email = 'feed@x.vn'"""
    )
    second = guest.get(next_gallery_url(first_html)).get_data(as_text=True)
    third = guest.get(next_gallery_url(second)).get_data(as_text=True)
    assert gallery_numbers(second) == list(range(41, 17, -1))
    assert gallery_numbers(third) == list(range(17, 0, -1))
    assert next_gallery_url(third) is None


def test_gallery_next_page_rechecks_visibility_and_keeps_tag(app, admin_client, db):
    seed_gallery(db, 53)
    db.execute("UPDATE artworks SET visibility = 'internal' WHERE title = 'Tranh 1'")
    db.execute("UPDATE artworks SET status = 'pending' WHERE title = 'Tranh 2'")
    db.execute("UPDATE artworks SET deleted_at = now() WHERE title = 'Tranh 3'")
    tag = db.execute("INSERT INTO tags (name, type) VALUES ('Hội An', 'location') RETURNING id").fetchone()["id"]
    db.execute("INSERT INTO artwork_tags SELECT id, %s FROM artworks WHERE title <> 'Tranh 4'", (tag,))

    member = member_client(app, admin_client, "Lan", "lan@x.vn", status="break")
    first = member.get(f"/gallery?tag={tag}").get_data(as_text=True)
    next_url = next_gallery_url(first)
    assert next_url is not None and f"tag={tag}" in next_url
    assert f'href="/gallery?tag={tag}"' in first

    second = member.get(next_url).get_data(as_text=True)
    guest_second = app.test_client().get(next_url).get_data(as_text=True)
    # Cùng URL phân trang được mở với hai quyền khác nhau.
    assert gallery_numbers(second) == list(range(29, 5, -1))
    assert gallery_numbers(guest_second) == gallery_numbers(second)
    last_url = next_gallery_url(second)
    assert last_url is not None
    member_last = member.get(last_url).get_data(as_text=True)
    guest_last = app.test_client().get(last_url).get_data(as_text=True)
    assert gallery_numbers(member_last) == [5, 1]
    assert "/image/authenticated/" in member_last
    assert gallery_numbers(guest_last) == [5]
    assert "/image/authenticated/" not in guest_last
    assert next_gallery_url(member_last) is None
    assert next_gallery_url(guest_last) is None


def test_gallery_hides_next_link_for_exactly_one_page(app, db):
    seed_gallery(db, 24)
    html = app.test_client().get("/gallery").get_data(as_text=True)
    assert len(gallery_numbers(html)) == 24
    assert next_gallery_url(html) is None


@pytest.mark.parametrize("cursor", ["", "invalid", "2026-01-01~00000000-0000-0000-0000-000000000001"])
def test_gallery_rejects_invalid_cursors(app, cursor):
    assert app.test_client().get("/gallery", query_string={"cursor": cursor}).status_code == 400


def test_original_goes_private_untouched_public_copy_is_processed(app, admin_client, uploads, db):
    original = jpeg_bytes((3000, 2000))
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    assert post_artwork(m, data=original).status_code == 302

    orig_call, pub_call = uploads["put"]
    assert orig_call["type"] == "private" and orig_call["data"] == original  # nguyên bytes, không nén
    assert pub_call["type"] == "upload" and pub_call["data"] != original
    row = db.execute("SELECT * FROM artworks").fetchone()
    assert row["status"] == "pending" and row["original_id"] != row["public_id"]


def test_internal_artwork_uses_authenticated_delivery(app, admin_client, uploads):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, visibility="internal")
    assert uploads["put"][1]["type"] == "authenticated"


def test_guest_never_sees_internal_or_pending_but_member_sees_internal(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, title="Tranh công khai", visibility="public", tags="Chợ Bến Thành")
    post_artwork(m, title="Tranh nội bộ", visibility="internal", tags="Bí mật")
    post_artwork(m, title="Tranh chờ duyệt", visibility="public", tags="Chờ")
    pend = db.execute("SELECT id FROM artworks WHERE title='Tranh chờ duyệt'").fetchone()["id"]
    for r in db.execute("SELECT id FROM artworks WHERE id <> %s", (pend,)).fetchall():
        admin_client.post(f"/admin/review/{r['id']}", data={"decision": "approve"})

    guest = app.test_client().get("/gallery").get_data(as_text=True)
    assert "Tranh công khai" in guest
    assert "Tranh nội bộ" not in guest and "Tranh chờ duyệt" not in guest
    assert "/image/authenticated/" not in guest
    # tag của tranh nội bộ cũng không được lộ cho khách
    assert "Bí mật" not in guest and "Chợ Bến Thành" in guest

    member = m.get("/gallery").get_data(as_text=True)
    assert "Tranh nội bộ" in member and "Bí mật" in member and "/image/authenticated/" in member
    assert "Tranh chờ duyệt" not in member


def test_tag_filter(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, title="A", tags="Hội An")
    post_artwork(m, title="B", tags="Sài Gòn")
    approve_all(admin_client, db)
    tag = db.execute("SELECT id FROM tags WHERE name='Hội An'").fetchone()["id"]
    html = app.test_client().get(f"/gallery?tag={tag}").get_data(as_text=True)
    assert "<h3>A" in html and "<h3>B" not in html
    assert app.test_client().get("/gallery?tag=not-a-uuid").status_code == 404


def test_tags_are_deduped_case_insensitively_across_artworks(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, tags="Hội An, hội an ,  ")
    post_artwork(m, tags="HỘI AN")
    assert db.execute("SELECT count(*) AS n FROM tags").fetchone()["n"] == 1
    assert db.execute("SELECT count(*) AS n FROM artwork_tags").fetchone()["n"] == 2


def test_upload_validation_errors_do_not_touch_storage(app, admin_client, uploads, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    bad = m.post("/upload", data={"title": "x", "visibility": "public", "file": (io.BytesIO(b"junk"), "a.jpg")},
                 content_type="multipart/form-data")
    assert bad.status_code == 400 and "Không đọc được" in bad.get_data(as_text=True)
    assert post_artwork(m, title="").status_code == 400
    assert post_artwork(m, visibility="secret").status_code == 400
    assert post_artwork(m, tags="x" * 31).status_code == 400
    assert uploads["put"] == [] and db.execute("SELECT count(*) AS n FROM artworks").fetchone()["n"] == 0


def test_break_and_former_members_view_but_cannot_post(app, admin_client):
    for status in ("break", "former"):
        m = member_client(app, admin_client, status, f"{status}@x.vn", status=status)
        assert m.get("/gallery").status_code == 200
        assert m.get("/upload").status_code == 403
        assert post_artwork(m).status_code == 403


def test_guest_cannot_upload(app):
    assert post_artwork(app.test_client()).status_code == 302


def test_visibility_toggle_moves_cloudinary_asset_and_enforces_ownership(app, admin_client, uploads, db):
    owner = member_client(app, admin_client, "Lan", "lan@x.vn")
    other = member_client(app, admin_client, "Mai", "mai@x.vn")
    post_artwork(owner)
    a = db.execute("SELECT id, public_id FROM artworks").fetchone()

    assert other.post(f"/artworks/{a['id']}/visibility", data={"visibility": "internal"}).status_code == 403
    assert uploads["move"] == []
    owner.post(f"/artworks/{a['id']}/visibility", data={"visibility": "internal"})
    assert uploads["move"] == [(a["public_id"], "upload", "authenticated")]
    assert db.execute("SELECT visibility FROM artworks").fetchone()["visibility"] == "internal"
    owner.post(f"/artworks/{a['id']}/visibility", data={"visibility": "internal"})  # không đổi -> không move lại
    assert len(uploads["move"]) == 1
    assert owner.post(f"/artworks/{a['id']}/visibility", data={"visibility": "x"}).status_code == 400


def test_soft_delete_hides_artwork_and_keeps_row(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, title="Sẽ xóa")
    approve_all(admin_client, db)
    a = db.execute("SELECT id FROM artworks").fetchone()
    other = member_client(app, admin_client, "Mai", "mai@x.vn")
    assert other.post(f"/artworks/{a['id']}/delete").status_code == 403

    m.post(f"/artworks/{a['id']}/delete")
    row = db.execute("SELECT deleted_at FROM artworks").fetchone()
    assert row["deleted_at"] is not None
    assert "Sẽ xóa" not in app.test_client().get("/gallery").get_data(as_text=True)
    assert "Sẽ xóa" not in m.get("/me").get_data(as_text=True)


def test_admin_can_delete_others_artwork_and_it_is_audited(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m)
    a = db.execute("SELECT id FROM artworks").fetchone()
    admin_client.post(f"/artworks/{a['id']}/delete")
    assert db.execute("SELECT 1 FROM audit_logs WHERE action='artwork.delete'").fetchone()


def test_titles_are_escaped(app, admin_client, db):
    m = member_client(app, admin_client, "Lan", "lan@x.vn")
    post_artwork(m, title="<script>alert(1)</script>")
    approve_all(admin_client, db)
    html = app.test_client().get("/gallery").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
