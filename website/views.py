import os
from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from .models import get_db_connection, save_image, delete_image, allowed_file

views = Blueprint('views', __name__)


# ---------- basic routes ----------
@views.route('/')
def index():
    return render_template('index.html')


@views.route('/about')
def about():
    return render_template('about.html')


# ---------- artwork API ----------
@views.route('/api/artworks', methods=['GET'])
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


@views.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    file = request.files.get('file')
    title = request.form.get('title')
    artist = request.form.get('artist')
    desc = request.form.get('description')

    if not title or not artist:
        return jsonify({'error': 'Thiếu tiêu đề hoặc tên tác giả'}), 400

    if file and file.filename != '':
        if not allowed_file(file.filename):
            return jsonify({'error': 'Định dạng ảnh không được hỗ trợ'}), 400

        result = save_image(file, file.filename, current_app.config['UPLOAD_FOLDER'])
        if not result['success']:
            return jsonify({'error': f"Không xử lý được ảnh này ({result['error']}). Hãy thử lưu ảnh dưới dạng JPG/PNG rồi tải lại."}), 400

        conn = get_db_connection()
        # status mặc định 'pending': tranh cần admin duyệt ở /admin trước khi
        # hiển thị công khai (đúng với luồng duyệt tranh đã có sẵn trong hệ thống).
        conn.execute(
            'INSERT INTO artworks (title, artist, description, image_path, image_public_id, status, user_id) '
            'VALUES(?, ?, ?, ?, ?, ?, ?)',
            (title, artist, desc, result['path'], result['public_id'], 'pending', current_user.id),
        )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Đã gửi, chờ admin duyệt!'}), 200
    return jsonify({'error': 'Lỗi file'}), 400


@views.route('/upload')
def upload_page():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return render_template('upload.html')


# ---------- activities API ----------
@views.route('/api/activities', methods=['GET'])
def get_activities():
    conn = get_db_connection()
    photos = conn.execute('SELECT * FROM activities ORDER BY id DESC LIMIT 12').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in photos])


@views.route('/api/activity/upload', methods=['POST'])
@login_required
def upload_activity():
    if current_user.role not in ['admin', 'photographer']:
        return jsonify({'error': 'Không có quyền'}), 403

    album_id = request.form.get('album_id')
    files = request.files.getlist('files')

    conn = get_db_connection()
    skipped = []
    for file in files:
        if file and file.filename != '' and allowed_file(file.filename):
            result = save_image(file, f"activity_{file.filename}", current_app.config['UPLOAD_FOLDER'])
            if not result['success']:
                skipped.append(file.filename)
                continue
            conn.execute(
                'INSERT INTO activities (image_path, image_public_id, album_id) VALUES (?, ?, ?)',
                (result['path'], result['public_id'], album_id),
            )

    conn.commit()
    conn.close()
    if skipped:
        return jsonify({'message': 'OK', 'skipped': skipped}), 200
    return jsonify({'message': 'OK'})


@views.route('/upload-activity')
def upload_activity_page():
    if not current_user.is_authenticated or current_user.role not in ['admin', 'photographer']:
        return redirect(url_for('views.index'))

    conn = get_db_connection()
    albums = conn.execute('SELECT * FROM albums ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('activity.html', albums=albums)


@views.route('/api/activity/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_activity(id):
    if current_user.role not in ['admin', 'photographer']:
        return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    photo = conn.execute('SELECT * FROM activities WHERE id=?', (id,)).fetchone()
    if photo:
        delete_image(photo['image_path'], photo['image_public_id'] if 'image_public_id' in photo.keys() else None)
        conn.execute('DELETE FROM activities WHERE id=?', (id,))
        conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})


# ---------- announcements API ----------
@views.route('/api/announcements', methods=['GET'])
def get_announcements():
    conn = get_db_connection()
    notices = conn.execute('SELECT * FROM announcements ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in notices])


@views.route('/api/announcement/create', methods=['POST'])
@login_required
def create_announcement():
    if current_user.role != 'admin':
        return jsonify({'error': '403'}), 403

    title = request.form.get('title')
    content = request.form.get('content')
    event_time = request.form.get('event_time')
    location = request.form.get('location')
    file = request.files.get('file')

    if not title or not content:
        return jsonify({'error': 'Thiếu tiêu đề hoặc nội dung'}), 400

    image_path, image_public_id = None, None
    if file and file.filename != '':
        if not allowed_file(file.filename):
            return jsonify({'error': 'Định dạng ảnh không được hỗ trợ'}), 400
        result = save_image(file, f"notice_{file.filename}", current_app.config['UPLOAD_FOLDER'])
        if not result['success']:
            return jsonify({'error': f"Không xử lý được ảnh này ({result['error']})"}), 400
        image_path, image_public_id = result['path'], result['public_id']

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO announcements (title, content, event_time, location, image_path, image_public_id) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (title, content, event_time, location, image_path, image_public_id),
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})


@views.route('/api/announcement/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_announcement(id):
    if current_user.role != 'admin':
        return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    notice = conn.execute('SELECT * FROM announcements WHERE id = ?', (id,)).fetchone()
    if notice and notice['image_path']:
        delete_image(notice['image_path'], notice['image_public_id'] if 'image_public_id' in notice.keys() else None)
    conn.execute('DELETE FROM announcements WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})


# ---------- album API ----------
@views.route('/api/albums', methods=['GET'])
def get_albums():
    conn = get_db_connection()
    albums = conn.execute('SELECT * FROM albums ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in albums])


@views.route('/api/album/create', methods=['POST'])
@login_required
def create_album():
    if current_user.role not in ['admin', 'photographer']:
        return jsonify({'error': '403'}), 403

    title = request.form.get('title')
    file = request.files.get('cover')

    if not title or not file:
        return jsonify({'error': 'Thiếu thông tin'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Định dạng ảnh không được hỗ trợ'}), 400

    result = save_image(file, f"cover_{file.filename}", current_app.config['UPLOAD_FOLDER'])
    if not result['success']:
        return jsonify({'error': f"Không xử lý được ảnh bìa này ({result['error']}). Hãy thử ảnh JPG/PNG khác."}), 400

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO albums (title, cover_image, cover_public_id) VALUES (?, ?, ?)',
        (title, result['path'], result['public_id']),
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})


@views.route('/api/album/<int:id>/photos', methods=['GET'])
def get_album_photos(id):
    conn = get_db_connection()
    photos = conn.execute('SELECT * FROM activities WHERE album_id = ? ORDER BY id DESC', (id,)).fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in photos])


# ---------- admin dashboard ----------
@views.route('/admin')
@login_required
def admin_page():
    if current_user.role != 'admin':
        return "403", 403
    return render_template('admin.html')


@views.route('/api/admin/pending', methods=['GET'])
@login_required
def get_pending():
    if current_user.role != 'admin':
        return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    artworks = conn.execute("SELECT * FROM artworks WHERE status = 'pending' ORDER BY created_at ASC").fetchall()
    conn.close()
    return jsonify([dict(ix) for ix in artworks])


@views.route('/api/admin/approve/<int:id>', methods=['POST'])
@login_required
def approve_artwork(id):
    if current_user.role != 'admin':
        return jsonify({'error': '403'}), 403
    conn = get_db_connection()
    conn.execute("UPDATE artworks SET status = 'active' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})


# ---------- edit / delete / like ----------
@views.route('/api/artwork/edit/<int:id>', methods=['POST'])
@login_required
def user_edit_artwork(id):
    data = request.json or {}
    conn = get_db_connection()
    artwork = conn.execute('SELECT * FROM artworks WHERE id = ?', (id,)).fetchone()
    if not artwork:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    if current_user.role != 'admin' and current_user.id != artwork['user_id']:
        conn.close()
        return jsonify({'error': '403'}), 403

    conn.execute(
        'UPDATE artworks SET title=?, artist=?, description=? WHERE id=?',
        (data.get('title'), data.get('artist'), data.get('description'), id),
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'})


@views.route('/api/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_artwork(id):
    conn = get_db_connection()
    artwork = conn.execute('SELECT * FROM artworks WHERE id = ?', (id,)).fetchone()
    if artwork:
        if current_user.role != 'admin' and current_user.id != artwork['user_id']:
            conn.close()
            return jsonify({'error': '403'}), 403

        delete_image(artwork['image_path'], artwork['image_public_id'] if 'image_public_id' in artwork.keys() else None)
        conn.execute('DELETE FROM artworks WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Deleted'}), 200
    conn.close()
    return jsonify({'error': 'Not found'}), 404


@views.route('/api/artwork/<int:id>/comments', methods=['GET'])
def get_comments(id):
    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT c.id, c.content, c.created_at, c.user_id,
                  u.fullname, u.username, u.avatar
           FROM comments c JOIN users u ON u.id = c.user_id
           WHERE c.artwork_id = ? ORDER BY c.id ASC''',
        (id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@views.route('/api/artwork/<int:id>/comments', methods=['POST'])
@login_required
def add_comment(id):
    data = request.json or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Bình luận không được để trống'}), 400
    if len(content) > 500:
        return jsonify({'error': 'Bình luận quá dài (tối đa 500 ký tự)'}), 400

    conn = get_db_connection()
    artwork = conn.execute('SELECT id FROM artworks WHERE id = ?', (id,)).fetchone()
    if not artwork:
        conn.close()
        return jsonify({'error': 'Không tìm thấy tranh'}), 404

    conn.execute(
        'INSERT INTO comments (artwork_id, user_id, content) VALUES (?, ?, ?)',
        (id, current_user.id, content),
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'OK'}), 201


@views.route('/api/comment/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    conn = get_db_connection()
    comment = conn.execute('SELECT * FROM comments WHERE id = ?', (comment_id,)).fetchone()
    if not comment:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    if current_user.role != 'admin' and current_user.id != comment['user_id']:
        conn.close()
        return jsonify({'error': '403'}), 403

    conn.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})


@views.route('/api/like/<int:id>', methods=['POST'])
@login_required
def like_artwork(id):
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
    except Exception as e:
        return jsonify({'error': str(e)}), 500
