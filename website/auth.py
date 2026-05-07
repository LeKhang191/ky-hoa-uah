from flask import Blueprint, render_template, request, flash, jsonify
from flask_login import login_required, current_user
from flask_login import login_user, login_required, logout_user, current_user
from flask import Blueprint, render_template, request, flash, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from .models import get_db_connection, User

auth = Blueprint('auth', __name__)

# TODO:

# auth
@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        fullname = request.form['fullname']

        # admin
        role = 'user'
        if username.lower() in ['admin', 'lekhang']: role = 'admin'
        elif username.lower() in ['photo', 'media', 'nhiepanh']: role = 'photographer'

        conn = get_db_connection()
        if conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone():
            flash('Tên đăng nhập đã tồn tại!')
            return redirect(url_for('auth.signup'))

        hash_pass = generate_password_hash(password, method='pbkdf2:sha256')
        conn.execute('INSERT INTO users (username, password_hash, fullname, role) VALUES (?, ?, ?, ?)',
                     (username, hash_pass, fullname, role))
        conn.commit()
        conn.close()
        flash('Đăng ký thành công!')
        return redirect(url_for('auth.login'))
    return render_template('signup.html')

@auth.route('/login', methods=['GET', 'POST'])
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
            return redirect(url_for('views.index'))
        else:
            flash('Sai thông tin đăng nhập!')
    return render_template('login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('views.index'))

@auth.route('/profile', methods=['GET', 'POST'])
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

            # optimaze pics
            optimize_image(avatar_file, file_path)

            # create db link
            db_avatar_path = f"/static/uploads/{filename}"
            conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (db_avatar_path, current_user.id))

        conn.commit()
        flash('Update successfully!')
        return redirect(url_for('views.profile'))

    user = conn.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
    my_artworks = conn.execute('SELECT * FROM artworks WHERE user_id = ? ORDER BY id DESC', (current_user.id,)).fetchall()

    my_albums = []
    if current_user.role in ['admin', 'photographer']:
        my_albums = conn.execute('SELECT * FROM albums ORDER BY id DESC').fetchall()

    conn.close()
    avatar_url = user['avatar'] if user['avatar'] else f"https://ui-avatars.com/api/?name={user['fullname']}&background=random&size=200"
    return render_template('profile.html', user=user, avatar_url=avatar_url, artworks=my_artworks, albums=my_albums)
