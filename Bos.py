import sqlite3

conn = sqlite3.connect("petshop.db")
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE orders ADD COLUMN items TEXT")
    print("✅ 'items' kolonu eklendi.")
except sqlite3.OperationalError as e:
    print("⚠️ Zaten var veya başka hata:", e)

conn.commit()
conn.close()
