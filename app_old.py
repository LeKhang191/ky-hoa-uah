import os
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from PIL import Image

app = Flask(__name__)
app.secret_key = '1901'

# --- Config ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, 'my_database.db')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- CLASS USER ---
class User(UserMixin):
    def __init__(self, id, username, fullname, role, avatar):
        self.id = id
        self.username = username
        self.fullname = fullname
        self.role = role
        self.avatar = avatar

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user_data:
        return User(id=user_data['id'],
                    username=user_data['username'],
                    fullname=user_data['fullname'],
                    role=user_data['role'],
                    avatar=user_data['avatar'])
    return None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()

    # 1. Bảng Users
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email TEXT,
            fullname TEXT,
            role TEXT DEFAULT 'user',
            avatar TEXT
        )
    ''')

    # 2. Bảng Artworks
    conn.execute('''
        CREATE TABLE IF NOT EXISTS artworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            description TEXT,
            image_path TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Bảng Activities
    conn.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            album_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. Bảng Announcements
    conn.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            event_time TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 5. Bảng Likes
    conn.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER NOT NULL,
            artwork_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, artwork_id)
        )
    ''')

    # 6. Bảng Albums
    conn.execute('''
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            cover_image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    try: conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    except: pass
    try: conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
    except: pass
    try: conn.execute("ALTER TABLE artworks ADD COLUMN user_id INTEGER")
    except: pass
    try: conn.execute("ALTER TABLE activities ADD COLUMN album_id INTEGER")
    except: pass

    conn.commit()
    conn.close()

init_db()

# --- HÀM TỐI ƯU ẢNH ---
def optimize_image(file_stream, save_path):
    try:
        img = Image.open(file_stream)
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        max_width = 1200
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int((float(img.height) * float(ratio)))
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        img.save(save_path, optimize=True, quality=85)
        return True
    except:
        return False

# --- ROUTES CƠ BẢN ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

# --- AUTH (Đăng ký/Đăng nhập/Profile) ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        fullname = request.form['fullname']

        # PHÂN QUYỀN: Admin hoặc Photographer
        role = 'user'
        if username.lower() in ['admin', 'lekhang']: role = 'admin'
        elif username.lower() in ['photo', 'media', 'nhiepanh']: role = 'photographer'

        conn = get_db_connection()
        if conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone():
            flash('Tên đăng nhập đã tồn tại!')
            return redirect(url_for('signup'))

        hash_pass = generate_password_hash(password, method='pbkdf2:sha256')
        conn.execute('INSERT INTO users (username, password_hash, fullname, role) VALUES (?, ?, ?, ?)',
                     (username, hash_pass, fullname, role))
        conn.commit()
        conn.close()
        flash('Đăng ký thành công!')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            user_obj = User(user['id'], user['username'], user['fullname'], user['role'], user['avatar'])
            login_user(user_obj)
            return redirect(url_for('index'))
        else:
            flash('Sai thông tin đăng nhập!')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    if request.method == 'POST':
        new_fullname = request.form.get('fullname')
        avatar_file = request.files.get('avatar')

        if new_fullname:
            conn.execute('UPDATE users SET fullname = ? WHERE id = ?', (new_fullname, current_user.id))

        if avatar_file and avatar_file.filename != '':
            filename = secure_filename(f"avatar_{current_user.id}_{avatar_file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Tối ưu ảnh
            optimize_image(avatar_file, file_path)

            # Tạo đường dẫn DB
            db_avatar_path = f"/static/uploads/{filename}"
            conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (db_avatar_path, current_user.id))

        conn.commit()
        flash('Cập nhật thành công!')
        return redirect(url_for('profile'))

    user = conn.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
    my_artworks = conn.execute('SELECT * FROM artworks WHERE user_id = ? ORDER BY id DESC', (current_user.id,)).fetchall()

    my_albums = []
    if current_user.role in ['admin', 'photographer']:
        my_albums = conn.execute('SELECT * FROM albums ORDER BY id DESC').fetchall()

    conn.close()
    avatar_url = user['avatar'] if user['avatar'] else f"https://ui-avatars.com/api/?name={user['fullname']}&background=random&size=200"
    return render_template('profile.html', user=user, avatar_url=avatar_url, artworks=my_artworks, albums=my_albums)

# --- API TRANH (ARTWORKS) ---
@app.route('/api/artworks', methods=['GET'])
def get_artworks():
    conn = get_db_connection()
    query = '''SELECT a.*, (SELECT 1 FROM likes WHERE user_id = ? AND artwork_id = a.id) as is_liked
               FROM artworks a WHERE a.status = 'active' ORDER BY a.id DESC'''
    uid = current_user.id if current_user.is_authenticated else -1
    artworks = conn.execute(query, (uid,)).fetchall()
    conn.close()

    results = []
    for row in artworks:
        item = dict(row)
        item['is_liked'] = True if item['is_liked'] else False
        item['owner_id'] = item['user_id']
        results.append(item)
    return jsonify(results)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not current_user.is_authenticated: return jsonify({'error': 'Cần đăng nhập'}), 403
    file = request.files.get('file')
    title = request.form.get('title')
    artist = request.form.get('artist')
    desc = request.form.get('description')

    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        optimize_image(file, file_path)
        db_path = f"/static/uploads/{filename}"
        conn = get_db_connection()
        conn.execute('INSERT INTO artworks (title, artist, description, image_path, status, user_id) VALUES(?, ?, ?, ?, ?, ?)',
             (title, artist, desc, f"/static/uploads/{fname}", 'approved', current_user.id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'OK'}), 200
    return jsonify({'error': 'Lỗi file'}), 400

@app.route('/upload')
def upload_page():
    if not current_user.is_authenticated:
        return redirect(url_for('login')) # Chưa đăng nhập thì bắt đăng nhập
    return render_template('upload.html')

# --- API ẢNH SINH HOẠT (ACTIVITIES) ---
@app.route('/api/activities', methods=['GET'])
def get_activities():
    conn = get_db_connection()
    photos = conn.execute('SELECT * FROM activities ORDER BY id DESC LIMIT 12').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in photos])

@app.route('/api/activity/upload', methods=['POST'])
@login_required
def upload_activity():
    if current_user.role not in ['admin', 'photographer']:
        return jsonify({'error': 'Không có quyền'}), 403

    album_id = request.form.get('album_id')
    # SỬA LỖI getList -> getlist
    files = request.files.getlist('files')

    conn = get_db_connection()
    for file in files:
        if file and file.filename != '':
            fname = secure_filename(f"activity_{file.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            optimize_image(file, path)
            conn.execute('INSERT INTO activities (image_path, album_id) VALUES (?, ?)', (f"/static/uploads/{fname}", album_id))

    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

@app.route('/upload-activity')
def upload_activity_page():
    if not current_user.is_authenticated or current_user.role not in ['admin', 'photographer']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    albums = conn.execute('SELECT * FROM albums ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('activity.html', albums=albums)

@app.route('/api/activity/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_activity(id):
    if current_user.role not in ['admin', 'photographer']: return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    photo = conn.execute('SELECT * FROM activities WHERE id=?', (id,)).fetchone()
    if photo:
        try: os.remove(os.path.join(BASE_DIR, photo['image_path'].lstrip('/')))
        except: pass
        conn.execute('DELETE FROM activities WHERE id=?', (id,))
        conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# --- API BẢNG TIN (NOTICES) ---
@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    conn = get_db_connection()
    notices = conn.execute('SELECT * FROM announcements ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in notices])

@app.route('/api/announcement/create', methods=['POST'])
@login_required
def create_announcement():
    if current_user.role != 'admin': return jsonify({'error': '403'}), 403
    data = request.json
    conn = get_db_connection()
    conn.execute('INSERT INTO announcements (title, content, event_time, location) VALUES (?, ?, ?, ?)',
                 (data.get('title'), data.get('content'), data.get('event_time'), data.get('location')))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

@app.route('/api/announcement/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_announcement(id):
    if current_user.role != 'admin': return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    conn.execute('DELETE FROM announcements WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# --- API ALBUM ---
@app.route('/api/albums', methods=['GET'])
def get_albums():
    conn = get_db_connection()
    albums = conn.execute('SELECT * FROM albums ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in albums])

@app.route('/api/album/create', methods=['POST'])
@login_required
def create_album():
    if current_user.role not in ['admin', 'photographer']:
        return jsonify({'error': '403'}), 403

    title = request.form.get('title')
    file = request.files.get('cover')

    if not title or not file:
        return jsonify({'error': 'Thiếu thông tin'}), 400

    filename = secure_filename(f"cover_{file.filename}")
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    optimize_image(file, path)

    conn = get_db_connection()
    conn.execute('INSERT INTO albums (title, cover_image) VALUES (?, ?)', (title, f"/static/uploads/{filename}"))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

@app.route('/api/album/<int:id>/photos', methods=['GET'])
def get_album_photos(id):
    conn = get_db_connection()
    photos = conn.execute('SELECT * FROM activities WHERE album_id = ? ORDER BY id DESC', (id,)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in photos])


# --- ADMIN DUYỆT TRANH ---
@app.route('/admin')
@login_required
def admin_page():
    if current_user.role != 'admin': return "403", 403
    return render_template('admin.html')

@app.route('/api/admin/pending', methods=['GET'])
@login_required
def get_pending():
    if current_user.role != 'admin': return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    artworks = conn.execute("SELECT * FROM artworks WHERE status = 'pending' ORDER BY created_at ASC").fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in artworks])

@app.route('/api/admin/approve/<int:id>', methods=['POST'])
@login_required
def approve_artwork(id):
    if current_user.role != 'admin': return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    conn.execute("UPDATE artworks SET status = 'active' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

# --- CHỨC NĂNG CHUNG (Edit, Delete, Like) ---
@app.route('/api/artwork/edit/<int:id>', methods=['POST'])
@login_required
def user_edit_artwork(id):
    data = request.json
    conn = get_db_connection()
    artwork = conn.execute('SELECT * FROM artworks WHERE id = ?', (id,)).fetchone()
    if not artwork: return jsonify({'error': 'Not found'}), 404

    if current_user.role != 'admin' and current_user.id != artwork['user_id']:
        return jsonify({'error': '403'}), 403

    conn.execute('UPDATE artworks SET title=?, artist=?, description=? WHERE id=?',
                 (data.get('title'), data.get('artist'), data.get('description'), id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})

@app.route('/api/delete/<int:id>', methods=['DELETE'])
def delete_artwork(id):
    if not current_user.is_authenticated: return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    artwork = conn.execute('SELECT * FROM artworks WHERE id = ?', (id,)).fetchone()
    if artwork:
        if current_user.role != 'admin' and current_user.id != artwork['user_id']:
            return jsonify({'error': '403'}), 403

        try: os.remove(os.path.join(BASE_DIR, artwork['image_path'].lstrip('/')))
        except: pass
        conn.execute('DELETE FROM artworks WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Deleted'}), 200
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/like/<int:id>', methods=['POST'])
def like_artwork(id):
    if not current_user.is_authenticated: return jsonify({'error': 'login_required'}), 401
    try:
        conn = get_db_connection()
        user_id = current_user.id
        existing = conn.execute('SELECT * FROM likes WHERE user_id=? AND artwork_id=?', (user_id, id)).fetchone()
        if existing:
            conn.execute('DELETE FROM likes WHERE user_id=? AND artwork_id=?', (user_id, id))
            conn.execute('UPDATE artworks SET likes = likes - 1 WHERE id=?', (id,))
            liked = False
        else:
            conn.execute('INSERT INTO likes (user_id, artwork_id) VALUES (?,?)', (user_id, id))
            conn.execute('UPDATE artworks SET likes = likes + 1 WHERE id=?', (id,))
            liked = True
        conn.commit()
        new_likes = conn.execute('SELECT likes FROM artworks WHERE id=?', (id,)).fetchone()['likes']
        conn.close()
        return jsonify({'likes': new_likes, 'liked': liked}), 200
    except Exception as e: return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)