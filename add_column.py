import sqlite3

conn = sqlite3.connect("petshop.db")
cursor = conn.cursor()

# Gerekli sütunları ekle
try:
    cursor.execute("ALTER TABLE orders ADD COLUMN customer_name TEXT")
except: pass

try:
    cursor.execute("ALTER TABLE orders ADD COLUMN address TEXT")
except: pass

try:
    cursor.execute("ALTER TABLE orders ADD COLUMN note TEXT")
except: pass

conn.commit()
conn.close()

print("orders tablosu güncellendi.")
