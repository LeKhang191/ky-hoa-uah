import os
from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from . import db, storage

REQUIRED_CONFIG = ("SECRET_KEY", "DATABASE_URL", "CLOUDINARY_URL", "JOIN_FORM_URL")

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Vui lòng đăng nhập."


def create_app(test_config=None):
    config = {key: os.environ.get(key) for key in REQUIRED_CONFIG}
    config.update(test_config or {})
    missing = [key for key in REQUIRED_CONFIG if not config.get(key)]
    if missing:
        raise RuntimeError(f"Thiếu biến môi trường: {', '.join(missing)}")

    app = Flask(__name__)
    app.config.update(
        config,
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    storage.configure(config["CLOUDINARY_URL"])

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    from . import admin, auth, cli, gallery

    app.register_blueprint(gallery.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    cli.init_app(app)

    @app.template_filter("art_url")
    def art_url(artwork):
        return storage.url(artwork["public_id"], storage.DELIVERY_TYPE[artwork["visibility"]])

    @app.template_filter("img_url")
    def img_url(public_id):
        return storage.url(public_id, "upload")

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error_page(e):
        return render_template("error.html", e=e), e.code

    return app


def schema_path():
    return Path(__file__).resolve().parent.parent / "schema.sql"
