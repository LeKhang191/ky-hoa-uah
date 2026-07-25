import os
from flask import Blueprint, request, render_template_string, flash
from flask_login import login_required, current_user

from .models import get_db_connection

admin_setup = Blueprint('admin_setup', __name__)

FORM_HTML = '''
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Admin Setup</title>
  <style>
    body { font-family: sans-serif; max-width: 420px; margin: 60px auto; padding: 0 16px; }
    input { width: 100%; padding: 10px; margin-bottom: 12px; box-sizing: border-box; }
    button { padding: 10px 20px; cursor: pointer; }
    .msg { padding: 10px; margin-bottom: 16px; border-radius: 6px; }
    .ok { background: #d4edda; color: #155724; }
    .err { background: #f8d7da; color: #721c24; }
  </style>
</head>
<body>
  <h2>Phong quyen Admin (dung 1 lan)</h2>
  {% if message %}
    <div class="msg {{ 'ok' if success else 'err' }}">{{ message }}</div>
  {% endif %}
  <form method="POST">
    <label>Username can phong admin:</label>
    <input type="text" name="username" required>
    <label>Ma bi mat (ADMIN_SETUP_KEY):</label>
    <input type="password" name="secret" required>
    <button type="submit">Phong Admin</button>
  </form>
</body>
</html>
'''


@admin_setup.route('/admin-setup', methods=['GET', 'POST'])
def setup_admin():
    message = None
    success = False

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        secret = request.form.get('secret', '')
        expected_secret = os.environ.get('ADMIN_SETUP_KEY')

        if not expected_secret:
            message = "Server chua cau hinh ADMIN_SETUP_KEY. Vao Render > Environment de them bien nay."
        elif secret != expected_secret:
            message = "Ma bi mat khong dung."
        else:
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if not user:
                message = f"Khong tim thay username '{username}'. Hay dang ky tai khoan nay truoc."
            else:
                conn.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
                conn.commit()
                message = f"Da phong '{username}' thanh admin! Dang xuat va dang nhap lai de thay menu Admin."
                success = True
            conn.close()

    return render_template_string(FORM_HTML, message=message, success=success)
