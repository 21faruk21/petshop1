import sqlite3

conn = sqlite3.connect("petshop.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price REAL,
    image TEXT,
    category TEXT,
    subcategory TEXT,
    description TEXT,
    in_stock INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT,
    items TEXT,
    total_price REAL,
    customer_name TEXT,
    address TEXT,
    note TEXT
)
""")

conn.commit()
conn.close()
