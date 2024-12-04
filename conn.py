import sqlite3

# إنشاء اتصال بقاعدة البيانات
conn = sqlite3.connect("users.db")
cursor = conn.cursor()

# إنشاء جدول لحفظ معلومات الأعضاء
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_admin INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0       
)
""")

conn.commit()
conn.close()
