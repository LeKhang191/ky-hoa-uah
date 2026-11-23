from datetime import datetime
from uuid import UUID

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db, images, storage
from .security import poster_required

bp = Blueprint("gallery", __name__)

TAG_FIELDS = (("location", "Địa điểm"), ("material", "Chất liệu"), ("session", "Buổi thực chiến"))
MAX_TAGS_PER_TYPE = 8
GALLERY_PAGE_SIZE = 24

# Khách chỉ thấy tranh công khai; thành viên đăng nhập (kể cả break/former) thấy cả nội bộ.
VISIBLE = """a.status = 'approved' AND a.deleted_at IS NULL AND (%(internal)s OR a.visibility = 'public')"""


@bp.after_request
def prevent_gallery_caching(response):
    if request.endpoint in {"gallery.gallery", "gallery.artwork_detail"}:
        response.cache_control.private = True
        response.cache_control.no_store = True
    return response


def _parse_tags(form):
    parsed = []
    for type_, _label in TAG_FIELDS:
        names, seen = [], set()
        for raw in form.get(f"tags_{type_}", "").split(","):
            name = raw.strip()
            if not name or name.lower() in seen:
                continue
            if len(name) > 30:
                raise ValueError("Mỗi thẻ tối đa 30 ký tự.")
            seen.add(name.lower())
            names.append(name)
        if len(names) > MAX_TAGS_PER_TYPE:
            raise ValueError(f"Tối đa {MAX_TAGS_PER_TYPE} thẻ mỗi loại.")
        parsed += [(name, type_) for name in names]
    return parsed


@bp.route("/")
def home():
    news = db.rows("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 5")
    albums = db.rows("SELECT * FROM albums ORDER BY created_at DESC LIMIT 6")
    return render_template("home.html", news=news, albums=albums)


@bp.route("/gallery")
def gallery():
    tag_id = request.args.get("tag")
    if tag_id:
        try:
            tag_id = str(UUID(tag_id))
        except ValueError:
            abort(404)
    else:
        tag_id = None

    cursor = request.args.get("cursor")
    before_time = before_id = None
    if cursor is not None:
        try:
            timestamp, artwork_id = cursor.split("~", 1)
            before_time = datetime.fromisoformat(timestamp)
            before_id = UUID(artwork_id)
            if before_time.tzinfo is None:
                raise ValueError
        except ValueError:
            abort(400, description="Mốc phân trang không hợp lệ.")

    params = {
        "internal": current_user.is_authenticated,
        "tag": tag_id,
        "before_time": before_time,
        "before_id": before_id,
        "limit": GALLERY_PAGE_SIZE + 1,
    }
    artworks = db.rows(
        f"""WITH page AS (
                SELECT a.id, a.created_at, a.author_id, a.title, a.public_id, a.visibility
                FROM artworks a
                WHERE {VISIBLE}
                  AND (%(tag)s::uuid IS NULL OR EXISTS (
                        SELECT 1 FROM artwork_tags x WHERE x.artwork_id = a.id AND x.tag_id = %(tag)s::uuid))
                  AND (%(before_time)s::timestamptz IS NULL OR
                       (a.created_at, a.id) < (%(before_time)s::timestamptz, %(before_id)s::uuid))
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %(limit)s
            )
            SELECT a.*, p.full_name AS author_name
            FROM page a
            JOIN profiles p ON p.id = a.author_id
            ORDER BY a.created_at DESC, a.id DESC""",
        params,
    )
    next_cursor = None
    if len(artworks) > GALLERY_PAGE_SIZE:
        artworks = artworks[:GALLERY_PAGE_SIZE]
        last = artworks[-1]
        next_cursor = f"{last['created_at'].isoformat()}~{last['id']}"

    tags = db.rows(
        f"""SELECT DISTINCT t.id, t.name, t.type
            FROM tags t
            JOIN artwork_tags at ON at.tag_id = t.id
            JOIN artworks a ON a.id = at.artwork_id
            WHERE {VISIBLE}
            ORDER BY t.type, t.name""",
        params,
    )
    return render_template(
        "gallery.html",
        artworks=artworks,
        tags=tags,
        active_tag=tag_id,
        next_cursor=next_cursor,
        cursor=cursor,
    )


@bp.route("/artworks/<uuid:artwork_id>")
def artwork_detail(artwork_id):
    artwork = db.row(
        f"""SELECT a.id, a.title, a.description, a.public_id, a.visibility, p.full_name AS author_name
            FROM artworks a
            JOIN profiles p ON p.id = a.author_id
            WHERE a.id = %(id)s AND {VISIBLE}""",
        {"id": artwork_id, "internal": current_user.is_authenticated},
    )
    if artwork is None:
        abort(404)

    tags = db.rows(
        """SELECT t.id, t.name
           FROM artwork_tags at
           JOIN tags t ON t.id = at.tag_id
           WHERE at.artwork_id = %s
           ORDER BY t.type, t.name""",
        (artwork_id,),
    )
    gallery_url = url_for(
        "gallery.gallery",
        tag=request.args.get("tag"),
        cursor=request.args.get("cursor"),
        _anchor=f"artwork-{artwork_id}",
    )
    return render_template("artwork_detail.html", artwork=artwork, tags=tags, gallery_url=gallery_url)


@bp.route("/albums/<uuid:album_id>")
def album(album_id):
    a = db.row("SELECT * FROM albums WHERE id = %s", (album_id,))
    if not a:
        abort(404)
    photos = db.rows("SELECT * FROM album_photos WHERE album_id = %s ORDER BY created_at DESC", (album_id,))
    return render_template("album.html", album=a, photos=photos)


@bp.route("/upload", methods=["GET", "POST"])
@poster_required
def upload():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        visibility = request.form.get("visibility", "")
        file = request.files.get("file")
        try:
            if not title or len(title) > 120:
                raise ValueError("Tiêu đề cần từ 1 đến 120 ký tự.")
            if visibility not in storage.DELIVERY_TYPE:
                raise ValueError("Chế độ hiển thị không hợp lệ.")
            if not file or not file.filename:
                raise ValueError("Chưa chọn ảnh.")
            tags = _parse_tags(request.form)
            original = file.read()
            public_bytes = images.public_artwork(original)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("upload.html", tag_fields=TAG_FIELDS), 400

        original_id = storage.put(original, "ky-hoa/original", "private")
        public_id = storage.put(public_bytes, "ky-hoa/public", storage.DELIVERY_TYPE[visibility])
        artwork = db.row(
            """INSERT INTO artworks (author_id, title, description, original_id, public_id, visibility)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (current_user.id, title, request.form.get("description", "").strip() or None,
             original_id, public_id, visibility),
        )
        for name, type_ in tags:
            tag = db.row(
                """INSERT INTO tags (name, type) VALUES (%s, %s)
                   ON CONFLICT ((lower(name)), type) DO UPDATE SET name = tags.name RETURNING id""",
                (name, type_),
            )
            db.run("INSERT INTO artwork_tags (artwork_id, tag_id) VALUES (%s, %s)", (artwork["id"], tag["id"]))
        flash("Đã gửi tranh, đang chờ ban chủ nhiệm duyệt.", "ok")
        return redirect(url_for("gallery.mine"))
    return render_template("upload.html", tag_fields=TAG_FIELDS)


@bp.route("/me")
@login_required
def mine():
    artworks = db.rows(
        "SELECT * FROM artworks WHERE author_id = %s AND deleted_at IS NULL ORDER BY created_at DESC",
        (current_user.id,),
    )
    return render_template("me.html", artworks=artworks)


def _own_artwork(artwork_id):
    a = db.row("SELECT * FROM artworks WHERE id = %s AND deleted_at IS NULL", (artwork_id,))
    if not a:
        abort(404)
    if str(a["author_id"]) != current_user.id and not current_user.is_admin:
        abort(403)
    return a


@bp.route("/artworks/<uuid:artwork_id>/visibility", methods=["POST"])
@login_required
def set_visibility(artwork_id):
    a = _own_artwork(artwork_id)
    target = request.form.get("visibility", "")
    if target not in storage.DELIVERY_TYPE:
        abort(400)
    if target != a["visibility"]:
        storage.move(a["public_id"], storage.DELIVERY_TYPE[a["visibility"]], storage.DELIVERY_TYPE[target])
        db.run("UPDATE artworks SET visibility = %s WHERE id = %s", (target, artwork_id))
        if str(a["author_id"]) != current_user.id:
            db.audit("artwork.visibility", "artwork", artwork_id)
    return redirect(request.referrer or url_for("gallery.mine"))


@bp.route("/artworks/<uuid:artwork_id>/delete", methods=["POST"])
@login_required
def delete(artwork_id):
    a = _own_artwork(artwork_id)
    db.run("UPDATE artworks SET deleted_at = now() WHERE id = %s", (artwork_id,))
    if str(a["author_id"]) != current_user.id:
        db.audit("artwork.delete", "artwork", artwork_id)
    flash("Đã chuyển tranh vào thùng rác.", "ok")
    return redirect(request.referrer or url_for("gallery.mine"))
