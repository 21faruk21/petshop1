import sqlite3

conn = sqlite3.connect('petshop.db')
cursor = conn.cursor()

print("Product columns:")
cursor.execute('PRAGMA table_info(products)')
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

print("\nProduct 7 data:")
cursor.execute('SELECT * FROM products WHERE id = 7')
product = cursor.fetchone()
if product:
    cursor.execute('PRAGMA table_info(products)')
    columns = [row[1] for row in cursor.fetchall()]
    for i, col in enumerate(columns):
        print(f"  {col}: {product[i]}")
else:
    print("  Product 7 not found!")

conn.close()