import click
import psycopg
from flask import current_app

from . import codes, db, schema_path


def init_app(app):
    @app.cli.command("init-db")
    def init_db():
        """Áp schema.sql (idempotent)."""
        with psycopg.connect(current_app.config["DATABASE_URL"]) as c:
            c.execute(schema_path().read_text())
        click.echo("Đã áp schema.")

    @app.cli.command("create-admin")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    def create_admin(email, name):
        """Tạo admin đầu tiên và in mã kích hoạt. Admin vào /activate để đặt mật khẩu."""
        row = db.row(
            "INSERT INTO profiles (full_name, email, role) VALUES (%s, %s, 'admin') RETURNING id",
            (name, email),
        )
        code = codes.issue(row["id"])
        db.audit("admin.bootstrap", "profile", row["id"])
        click.echo(f"Mã kích hoạt (hiệu lực 72 giờ): {code}")
