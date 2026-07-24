"""
Script tạo tài khoản admin đầu tiên (chạy 1 lần, thủ công trên server).
Dùng thay cho việc "tự phong admin bằng username" trong signup — an toàn hơn
vì chỉ ai có quyền truy cập server/console mới chạy được script này.

Cách dùng:
    python create_admin.py
"""
import getpass
from werkzeug.security import generate_password_hash
from website.models import get_db_connection, init_db

def main():
    init_db()
    username = input("Username admin: ").strip()
    fullname = input("Họ tên hiển thị: ").strip()
    password = getpass.getpass("Mật khẩu: ")

    conn = get_db_connection()
    existing = conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        print(f"Đã cập nhật '{username}' thành admin.")
        conn.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
    else:
        hash_pass = generate_password_hash(password, method='pbkdf2:sha256')
        conn.execute(
            'INSERT INTO users (username, password_hash, fullname, role) VALUES (?, ?, ?, ?)',
            (username, hash_pass, fullname, 'admin'),
        )
        print(f"Đã tạo tài khoản admin '{username}'.")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    main()
