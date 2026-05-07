import sqlite3

conn = sqlite3.connect('my_database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT id, username, fullname, role, password_hash FROM users")
rows = cursor.fetchall()

if not rows:
    print("--- Database hiện tại chưa có tài khoản nào ---")
else:
    print("DANH SÁCH TÀI KHOẢN VÀ MẬT KHẨU:")
    print("-" * 100)
    for row in rows:
        short_hash = row['password_hash'][:35] + "..." 
        print(f"ID: {row['id']:<3} | User: {row['username']:<10} | Role: {row['role']:<10} | Hash: {short_hash}")

conn.close()