import csv
import io

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from . import codes, db, images, storage
from .security import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

STATUSES = ("active", "break", "former")
MAX_IMPORT_ROWS = 1000
MAX_ALBUM_UPLOAD = 20


@bp.before_request
@admin_required
def _guard():
    pass


@bp.route("/")
def dashboard():
    pending = db.row("SELECT count(*) AS n FROM artworks WHERE status = 'pending' AND deleted_at IS NULL")["n"]
    members = db.rows("SELECT status, count(*) AS n FROM profiles GROUP BY status ORDER BY status")
    return render_template("admin/dashboard.html", pending=pending, members=members)


# ---------- thành viên ----------
@bp.route("/members")
def members():
    rows = db.rows(
        """SELECT p.*, (SELECT count(*) FROM activation_codes c WHERE c.profile_id = p.id
                        AND c.used_at IS NULL AND c.revoked_at IS NULL AND c.expires_at > now()) AS live_codes
           FROM profiles p ORDER BY p.created_at DESC"""
    )
    return render_template("admin/members.html", members=rows, statuses=STATUSES)


@bp.route("/members/create", methods=["POST"])
def create_member():
    name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "active")
    if not name or not email or "@" not in email or status not in STATUSES:
        flash("Thông tin thành viên không hợp lệ.", "error")
        return redirect(url_for("admin.members"))
    if db.row("SELECT 1 FROM profiles WHERE lower(email) = lower(%s)", (email,)):
        flash("Email này đã có tài khoản.", "error")
        return redirect(url_for("admin.members"))
    p = db.row(
        "INSERT INTO profiles (full_name, email, status) VALUES (%s, %s, %s) RETURNING id", (name, email, status)
    )
    code = codes.issue(p["id"])
    db.audit("member.create", "profile", p["id"])
    flash(f"Mã kích hoạt cho {name}: {code} (hết hạn sau 72 giờ, chỉ hiện một lần).", "ok")
    return redirect(url_for("admin.members"))


def _other_member(profile_id):
    """Admin không tự khóa/đổi quyền chính mình để tránh mất toàn bộ quyền quản trị."""
    if str(profile_id) == current_user.id:
        abort(400)
    p = db.row("SELECT * FROM profiles WHERE id = %s", (profile_id,))
    if not p:
        abort(404)
    return p


@bp.route("/members/<uuid:profile_id>/status", methods=["POST"])
def set_status(profile_id):
    _other_member(profile_id)
    status = request.form.get("status", "")
    if status not in STATUSES:
        abort(400)
    db.run("UPDATE profiles SET status = %s WHERE id = %s", (status, profile_id))
    db.audit(f"member.status.{status}", "profile", profile_id)
    return redirect(url_for("admin.members"))


@bp.route("/members/<uuid:profile_id>/role", methods=["POST"])
def set_role(profile_id):
    _other_member(profile_id)
    role = request.form.get("role", "")
    if role not in ("member", "admin"):
        abort(400)
    db.run("UPDATE profiles SET role = %s WHERE id = %s", (role, profile_id))
    db.audit(f"member.role.{role}", "profile", profile_id)
    return redirect(url_for("admin.members"))


@bp.route("/members/<uuid:profile_id>/lock", methods=["POST"])
def toggle_lock(profile_id):
    p = _other_member(profile_id)
    db.run("UPDATE profiles SET is_locked = %s WHERE id = %s", (not p["is_locked"], profile_id))
    db.audit("member.unlock" if p["is_locked"] else "member.lock", "profile", profile_id)
    return redirect(url_for("admin.members"))


@bp.route("/members/<uuid:profile_id>/reissue", methods=["POST"])
def reissue_code(profile_id):
    p = db.row("SELECT * FROM profiles WHERE id = %s", (profile_id,))
    if not p:
        abort(404)
    code = codes.issue(profile_id)
    db.audit("code.reissue", "profile", profile_id)
    flash(f"Mã kích hoạt mới cho {p['full_name']}: {code} (hết hạn sau 72 giờ, chỉ hiện một lần).", "ok")
    return redirect(url_for("admin.members"))


@bp.route("/members/<uuid:profile_id>/revoke", methods=["POST"])
def revoke_code(profile_id):
    if not db.row("SELECT 1 FROM profiles WHERE id = %s", (profile_id,)):
        abort(404)
    codes.revoke_unused(profile_id)
    db.audit("code.revoke", "profile", profile_id)
    return redirect(url_for("admin.members"))


@bp.route("/import", methods=["GET", "POST"])
def import_members():
    if request.method == "GET":
        return render_template("admin/import.html", errors=None, created=None)

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Chưa chọn file CSV.", "error")
        return render_template("admin/import.html", errors=None, created=None), 400
    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("File phải được lưu dạng UTF-8 (Google Sheet: Tải xuống > CSV).", "error")
        return render_template("admin/import.html", errors=None, created=None), 400

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"full_name", "email"} <= set(reader.fieldnames):
        flash("File cần có cột full_name và email (cột status là tùy chọn).", "error")
        return render_template("admin/import.html", errors=None, created=None), 400

    parsed, errors, seen = [], [], set()
    for line_no, r in enumerate(reader, start=2):
        name = (r.get("full_name") or "").strip()
        email = (r.get("email") or "").strip()
        status = (r.get("status") or "active").strip() or "active"
        if not name or "@" not in email:
            errors.append(f"Dòng {line_no}: thiếu tên hoặc email không hợp lệ.")
        elif status not in STATUSES:
            errors.append(f"Dòng {line_no}: status '{status}' không hợp lệ.")
        elif email.lower() in seen:
            errors.append(f"Dòng {line_no}: email {email} bị trùng trong file.")
        elif db.row("SELECT 1 FROM profiles WHERE lower(email) = lower(%s)", (email,)):
            errors.append(f"Dòng {line_no}: email {email} đã có tài khoản.")
        else:
            seen.add(email.lower())
            parsed.append((name, email, status))
    if len(parsed) + len(errors) > MAX_IMPORT_ROWS:
        errors.append(f"File vượt quá {MAX_IMPORT_ROWS} dòng.")
    if not parsed and not errors:
        errors.append("File không có dòng dữ liệu nào.")
    if errors:  # all-or-nothing: một dòng sai thì không tạo ai
        return render_template("admin/import.html", errors=errors, created=None), 400

    created = []
    for name, email, status in parsed:
        p = db.row(
            "INSERT INTO profiles (full_name, email, status) VALUES (%s, %s, %s) RETURNING id", (name, email, status)
        )
        created.append({"name": name, "email": email, "code": codes.issue(p["id"])})
    db.audit("member.import", "profile", None)
    return render_template("admin/import.html", errors=None, created=created)


# ---------- duyệt tranh ----------
@bp.route("/review")
def review():
    pending = db.rows(
        """SELECT a.*, p.full_name AS author_name FROM artworks a JOIN profiles p ON p.id = a.author_id
           WHERE a.status = 'pending' AND a.deleted_at IS NULL ORDER BY a.created_at"""
    )
    return render_template("admin/review.html", artworks=pending)


@bp.route("/review/<uuid:artwork_id>", methods=["POST"])
def decide(artwork_id):
    decision = request.form.get("decision")
    reason = request.form.get("reason", "").strip() or None
    if decision == "approve":
        status, reason = "approved", None
    elif decision == "reject":
        if not reason:
            flash("Cần nhập lý do khi từ chối.", "error")
            return redirect(url_for("admin.review"))
        status = "rejected"
    else:
        abort(400)
    if not db.run(
        "UPDATE artworks SET status = %s, reject_reason = %s WHERE id = %s AND status = 'pending'",
        (status, reason, artwork_id),
    ):
        abort(404)
    db.audit(f"artwork.{status}", "artwork", artwork_id)
    return redirect(url_for("admin.review"))


# ---------- bảng tin ----------
@bp.route("/news", methods=["GET", "POST"])
def news():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        type_ = request.form.get("type", "")
        if not title or not body or type_ not in ("news", "event"):
            flash("Thông báo cần tiêu đề, nội dung và loại hợp lệ.", "error")
        else:
            n = db.row(
                "INSERT INTO notifications (title, body, type) VALUES (%s, %s, %s) RETURNING id", (title, body, type_)
            )
            db.audit("news.create", "notification", n["id"])
        return redirect(url_for("admin.news"))
    return render_template("admin/news.html", items=db.rows("SELECT * FROM notifications ORDER BY created_at DESC"))


@bp.route("/news/<uuid:news_id>/delete", methods=["POST"])
def delete_news(news_id):
    if not db.run("DELETE FROM notifications WHERE id = %s", (news_id,)):
        abort(404)
    db.audit("news.delete", "notification", news_id)
    return redirect(url_for("admin.news"))


# ---------- album ảnh sinh hoạt ----------
@bp.route("/albums", methods=["GET", "POST"])
def albums():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        cover = request.files.get("cover")
        try:
            if not title or len(title) > 120:
                raise ValueError("Tiêu đề album cần từ 1 đến 120 ký tự.")
            if not cover or not cover.filename:
                raise ValueError("Chưa chọn ảnh bìa.")
            cover_bytes = images.plain_resized(cover.read())
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.albums"))
        cover_id = storage.put(cover_bytes, "ky-hoa/albums", "upload")
        a = db.row("INSERT INTO albums (title, cover_path) VALUES (%s, %s) RETURNING id", (title, cover_id))
        db.audit("album.create", "album", a["id"])
        return redirect(url_for("admin.albums"))
    return render_template("admin/albums.html", albums=db.rows("SELECT * FROM albums ORDER BY created_at DESC"))


@bp.route("/albums/<uuid:album_id>/photos", methods=["POST"])
def add_photos(album_id):
    if not db.row("SELECT 1 FROM albums WHERE id = %s", (album_id,)):
        abort(404)
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files or len(files) > MAX_ALBUM_UPLOAD:
        flash(f"Chọn từ 1 đến {MAX_ALBUM_UPLOAD} ảnh.", "error")
        return redirect(url_for("admin.albums"))
    try:
        processed = [images.plain_resized(f.read()) for f in files]  # kiểm tra hết trước khi upload
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.albums"))
    for data in processed:
        path = storage.put(data, "ky-hoa/albums", "upload")
        db.run(
            "INSERT INTO album_photos (album_id, uploaded_by, image_path) VALUES (%s, %s, %s)",
            (album_id, current_user.id, path),
        )
    db.audit("album.add_photos", "album", album_id)
    flash(f"Đã thêm {len(processed)} ảnh.", "ok")
    return redirect(url_for("admin.albums"))


# ---------- nhật ký ----------
@bp.route("/logs")
def logs():
    rows = db.rows(
        """SELECT l.*, p.full_name AS actor_name FROM audit_logs l LEFT JOIN profiles p ON p.id = l.actor_id
           ORDER BY l.created_at DESC LIMIT 200"""
    )
    return render_template("admin/logs.html", logs=rows)
