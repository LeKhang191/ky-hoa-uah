from functools import wraps

from flask import abort
from flask_login import UserMixin, current_user

from . import db, login_manager


class Profile(UserMixin):
    def __init__(self, r):
        self.id = str(r["id"])
        self.full_name = r["full_name"]
        self.email = r["email"]
        self.role = r["role"]
        self.status = r["status"]

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def can_post(self):
        return self.status == "active"


@login_manager.user_loader
def load_profile(profile_id):
    r = db.row("SELECT * FROM profiles WHERE id = %s AND NOT is_locked", (profile_id,))
    return Profile(r) if r else None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def poster_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.can_post:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
