import os
import io
import sqlite3
from flask_login import UserMixin
from PIL import Image

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
DB_PATH = os.path.join(ROOT_DIR, 'my_database.db')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# --- Cloudinary (lưu ảnh vĩnh viễn, không mất khi Render restart) ---
# Chỉ kích hoạt nếu có biến môi trường CLOUDINARY_URL (đặt trên Render, KHÔNG hardcode ở đây).
# Nếu chưa cấu hình, hệ thống tự động lưu ảnh vào ổ đĩa local như cũ (vẫn hoạt động bình thường,
# chỉ là ảnh sẽ mất khi Render free tier restart).
CLOUDINARY_ENABLED = bool(os.environ.get('CLOUDINARY_URL'))
if CLOUDINARY_ENABLED:
    import cloudinary
    import cloudinary.uploader
    # cloudinary.config() tự đọc CLOUDINARY_URL từ biến môi trường, không cần truyền tay.
    cloudinary.config(secure=True)


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
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Tạo các bảng nếu chưa tồn tại. Gọi an toàn nhiều lần (idempotent)."""
    conn = get_db_connection()

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

    # Nâng cấp nhẹ nhàng cho DB đã tồn tại từ trước (không có cột image_public_id/cover_public_id)
    for table, col in [('artworks', 'image_public_id'), ('activities', 'image_public_id'), ('albums', 'cover_public_id')]:
        try:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} TEXT')
        except sqlite3.OperationalError:
            pass  # cột đã tồn tại rồi

    conn.commit()
    conn.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _process_image(file_stream, max_width=1200, quality=85):
    """Resize + nén ảnh, trả về (buffer_bytes, error). Không lưu ra đâu cả, chỉ xử lý trong bộ nhớ."""
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
    """
    Xử lý + lưu ảnh, tự động chọn Cloudinary (nếu đã cấu hình) hoặc ổ đĩa local.
    Trả về dict: {'success': bool, 'path': str, 'public_id': str|None, 'error': str|None}
    'path' là giá trị lưu vào cột image_path trong DB (URL đầy đủ nếu Cloudinary, hoặc
    '/static/uploads/xxx.jpg' nếu lưu local).
    """
    buf, err = _process_image(file_stream)
    if buf is None:
        return {'success': False, 'path': None, 'public_id': None, 'error': err}

    if CLOUDINARY_ENABLED:
        try:
            result = cloudinary.uploader.upload(
                buf, folder="ky-hoa-uah", resource_type="image"
            )
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
    """Xóa ảnh khỏi Cloudinary (nếu có public_id) hoặc khỏi ổ đĩa local."""
    if public_id and CLOUDINARY_ENABLED:
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
    elif image_path and image_path.startswith('/static/uploads/'):
        try:
            local_path = os.path.join(CURRENT_DIR, image_path.lstrip('/').replace('static/', 'static/', 1))
            local_path = os.path.join(CURRENT_DIR, 'static', 'uploads', os.path.basename(image_path))
            os.remove(local_path)
        except Exception:
            pass
