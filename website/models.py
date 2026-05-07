import os
import sqlite3
from flask_login import UserMixin

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
DB_PATH = os.path.join(ROOT_DIR, 'my_database.db')

class User(UserMixin):
    def __init__(self, id, username, fullname, role, avatar):
        self.id = id
        self.username = username
        self.fullname = fullname
        self.role = role
        self.avatar = avatar

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn