from uuid import UUID

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db, images, storage
from .security import poster_required

bp = Blueprint("gallery", __name__)

TAG_FIELDS = (("location", "Địa điểm"), ("material", "Chất liệu"), ("session", "Buổi thực chiến"))
MAX_TAGS_PER_TYPE = 8

# Khách chỉ thấy tranh công khai; thành viên đăng nhập (kể cả break/former) thấy cả nội bộ.
VISIBLE = """a.status = 'approved' AND a.deleted_at IS NULL AND (%(internal)s OR a.visibility = 'public')"""


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
            UUID(tag_id)
        except ValueError:
            abort(404)
    params = {"internal": current_user.is_authenticated, "tag": tag_id}
    artworks = db.rows(
        f"""SELECT a.*, p.full_name AS author_name,
                   COALESCE(array_agg(t.name ORDER BY t.type, t.name) FILTER (WHERE t.id IS NOT NULL), '{{}}') AS tag_names
            FROM artworks a
            JOIN profiles p ON p.id = a.author_id
            LEFT JOIN artwork_tags at ON at.artwork_id = a.id
            LEFT JOIN tags t ON t.id = at.tag_id
            WHERE {VISIBLE}
              AND (%(tag)s::uuid IS NULL OR EXISTS (
                    SELECT 1 FROM artwork_tags x WHERE x.artwork_id = a.id AND x.tag_id = %(tag)s::uuid))
            GROUP BY a.id, p.full_name
            ORDER BY a.created_at DESC LIMIT 60""",
        params,
    )
    tags = db.rows(
        f"""SELECT DISTINCT t.id, t.name, t.type
            FROM tags t
            JOIN artwork_tags at ON at.tag_id = t.id
            JOIN artworks a ON a.id = at.artwork_id
            WHERE {VISIBLE}
            ORDER BY t.type, t.name""",
        params,
    )
    return render_template("gallery.html", artworks=artworks, tags=tags, active_tag=tag_id)


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
