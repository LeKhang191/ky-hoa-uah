import sqlite3

def init_db():
    conn = sqlite3.connect('my_database.db')
    
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, email TEXT, fullname TEXT, role TEXT DEFAULT 'user', avatar TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS artworks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, artist TEXT NOT NULL, description TEXT, image_path TEXT NOT NULL, likes INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, image_path TEXT NOT NULL, album_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS announcements (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, event_time TEXT, location TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS likes (user_id INTEGER NOT NULL, artwork_id INTEGER NOT NULL, PRIMARY KEY (user_id, artwork_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS albums (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, cover_image TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    conn.commit()
    conn.close()
    print("Creating new DB.")

if __name__ == '__main__':
    init_db()