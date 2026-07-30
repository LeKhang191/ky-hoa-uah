import os
import io
import re
import sqlite3
from flask_login import UserMixin
from PIL import Image

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
DB_PATH = os.path.join(ROOT_DIR, 'my_database.db')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# --- Cloudinary (lưu ảnh vĩnh viễn) ---
CLOUDINARY_ENABLED = bool(os.environ.get('CLOUDINARY_URL'))
if CLOUDINARY_ENABLED:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(secure=True)

# --- Database: Supabase/PostgreSQL (production, vĩnh viễn) hoặc SQLite (local dev) ---
# Có biến môi trường DATABASE_URL (Supabase) -> dùng Postgres.
# Không có -> tự động dùng file my_database.db như cũ (không ảnh hưởng lúc code ở máy nhà).
DATABASE_URL = os.environ.get('DATABASE_URL')
IS_POSTGRES = bool(DATABASE_URL)

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras


class User(UserMixin):
    def __init__(self, id, username, fullname, role, avatar):
        self.id = id
        self.username = username
        self.fullname = fullname
        self.role = role
        self.avatar = avatar


class _DBConnection:
    """
    Lớp bọc để website/views.py và website/auth.py có thể dùng chung 1 cách viết
    conn.execute(query, params) / conn.commit() / conn.close() với dấu '?' quen thuộc,
    bất kể phía dưới đang chạy SQLite (dev) hay PostgreSQL (Supabase, production).
    KHÔNG cần sửa gì ở các file views.py/auth.py/admin_setup.py.
    """
    def __init__(self, raw_conn, is_postgres):
        self._conn = raw_conn
        self.is_postgres = is_postgres

    def execute(self, query, params=()):
        if self.is_postgres:
            query = query.replace('?', '%s')
            cur = self._conn.cursor()
            cur.execute(query, params)
            return cur
        else:
            return self._conn.execute(query, params)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass


def get_db_connection():
    if IS_POSTGRES:
        raw = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return _DBConnection(raw, True)
    else:
        raw = sqlite3.connect(DB_PATH)
        raw.row_factory = sqlite3.Row
        raw.execute('PRAGMA foreign_keys = ON')
        return _DBConnection(raw, False)


def init_db():
    """Tạo các bảng nếu chưa tồn tại. Gọi an toàn nhiều lần (idempotent)."""
    conn = get_db_connection()

    if IS_POSTGRES:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email TEXT,
            fullname TEXT,
            role TEXT DEFAULT 'user',
            avatar TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS artworks (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            description TEXT,
            image_path TEXT NOT NULL,
            image_public_id TEXT,
            likes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS activities (
            id SERIAL PRIMARY KEY,
            image_path TEXT NOT NULL,
            image_public_id TEXT,
            album_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS announcements (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            event_time TEXT,
            location TEXT,
            image_path TEXT,
            image_public_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER NOT NULL,
            artwork_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, artwork_id)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS albums (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            cover_image TEXT,
            cover_public_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            artwork_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
    else:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email TEXT,
            fullname TEXT,
            role TEXT DEFAULT 'user',
            avatar TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS artworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            description TEXT,
            image_path TEXT NOT NULL,
            image_public_id TEXT,
            likes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            image_public_id TEXT,
            album_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            event_time TEXT,
            location TEXT,
            image_path TEXT,
            image_public_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER NOT NULL,
            artwork_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, artwork_id)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            cover_image TEXT,
            cover_public_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artwork_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        for table, col in [('artworks', 'image_public_id'), ('activities', 'image_public_id'), ('albums', 'cover_public_id'), ('announcements', 'image_path'), ('announcements', 'image_public_id')]:
            try:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} TEXT')
            except sqlite3.OperationalError:
                pass
        conn.commit()

    conn.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _process_image(file_stream, max_width=1200, quality=85):
    try:
        img = Image.open(file_stream)
        img.load()
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, 'JPEG', optimize=True, quality=quality)
        buf.seek(0)
        return buf, None
    except Exception as e:
        return None, str(e)


def save_image(file_stream, filename_hint, upload_folder):
    buf, err = _process_image(file_stream)
    if buf is None:
        return {'success': False, 'path': None, 'public_id': None, 'error': err}

    if CLOUDINARY_ENABLED:
        try:
            result = cloudinary.uploader.upload(buf, folder="ky-hoa-uah", resource_type="image")
            return {'success': True, 'path': result['secure_url'], 'public_id': result['public_id'], 'error': None}
        except Exception as e:
            return {'success': False, 'path': None, 'public_id': None, 'error': f"Loi Cloudinary: {e}"}
    else:
        try:
            from werkzeug.utils import secure_filename
            base, _ = os.path.splitext(secure_filename(filename_hint))
            final_filename = f"{base}.jpg"
            save_path = os.path.join(upload_folder, final_filename)
            with open(save_path, 'wb') as f:
                f.write(buf.read())
            return {'success': True, 'path': f"/static/uploads/{final_filename}", 'public_id': None, 'error': None}
        except Exception as e:
            return {'success': False, 'path': None, 'public_id': None, 'error': str(e)}


def delete_image(image_path, public_id=None):
    if public_id and CLOUDINARY_ENABLED:
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
    elif image_path and image_path.startswith('/static/uploads/'):
        try:
            local_path = os.path.join(CURRENT_DIR, 'static', 'uploads', os.path.basename(image_path))
            os.remove(local_path)
        except Exception:
            pass
