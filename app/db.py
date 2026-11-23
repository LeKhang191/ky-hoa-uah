import psycopg
from flask import current_app, g, has_request_context
from flask_login import current_user
from psycopg.rows import dict_row


def conn():
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def rows(sql, params=None):
    with conn().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def row(sql, params=None):
    with conn().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def run(sql, params=None):
    with conn().cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def audit(action, target_type=None, target_id=None):
    actor = current_user.id if has_request_context() and current_user.is_authenticated else None
    run(
        "INSERT INTO audit_logs (actor_id, action, target_type, target_id) VALUES (%s, %s, %s, %s)",
        (actor, action, target_type, target_id),
    )


def _close(exc):
    db = g.pop("db", None)
    if db is None:
        return
    if exc:
        db.rollback()
    else:
        db.commit()
    db.close()


def init_app(app):
    app.teardown_appcontext(_close)
