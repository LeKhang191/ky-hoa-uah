from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import codes, db
from .security import Profile

bp = Blueprint("auth", __name__)

MIN_PASSWORD = 8


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        r = db.row("SELECT * FROM profiles WHERE lower(email) = lower(%s)", (email,))
        if r and r["password_hash"] and check_password_hash(r["password_hash"], password):
            if r["is_locked"]:
                flash("Tài khoản đang bị khóa. Hãy liên hệ ban chủ nhiệm.", "error")
            else:
                login_user(Profile(r))
                return redirect(url_for("gallery.home"))
        else:
            flash("Sai email hoặc mật khẩu.", "error")
    return render_template("login.html")


@bp.route("/activate", methods=["GET", "POST"])
def activate():
    """Lần đầu (hoặc khi admin cấp lại mã): email + mã kích hoạt -> tự đặt mật khẩu. Mã chỉ dùng một lần."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        code = request.form.get("code", "")
        password = request.form.get("password", "")
        if len(password) < MIN_PASSWORD:
            flash(f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.", "error")
            return render_template("activate.html")
        if password != request.form.get("password2", ""):
            flash("Hai mật khẩu không khớp.", "error")
            return render_template("activate.html")

        r = db.row(
            """SELECT c.id AS code_id, p.* FROM activation_codes c
               JOIN profiles p ON p.id = c.profile_id
               WHERE lower(p.email) = lower(%s) AND c.code_hash = %s
                 AND c.used_at IS NULL AND c.revoked_at IS NULL AND c.expires_at > now()
               FOR UPDATE OF c""",
            (email, codes.hash_code(code)),
        )
        if not r or r["is_locked"]:
            flash("Email hoặc mã kích hoạt không hợp lệ, đã dùng hoặc đã hết hạn.", "error")
            return render_template("activate.html")

        db.run("UPDATE activation_codes SET used_at = now() WHERE id = %s", (r["code_id"],))
        db.run(
            "UPDATE profiles SET password_hash = %s WHERE id = %s",
            (generate_password_hash(password), r["id"]),
        )
        login_user(Profile(r))
        flash("Kích hoạt thành công. Chào mừng bạn!", "ok")
        return redirect(url_for("gallery.home"))
    return render_template("activate.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("gallery.home"))
