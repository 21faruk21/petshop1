import sqlite3
import json

db = 'petshop.db'
conn = sqlite3.connect(db)
c = conn.cursor()
c.execute('SELECT id, subcategory FROM products')
rows = c.fetchall()
for id, sub in rows:
    if sub and not sub.strip().startswith('['):
        newsub = json.dumps([sub])
        c.execute('UPDATE products SET subcategory=? WHERE id=?', (newsub, id))
    elif sub and sub.strip().startswith('['):
        # Zaten JSON, dokunma
        pass
    else:
        c.execute('UPDATE products SET subcategory=? WHERE id=?', (json.dumps([]), id))
conn.commit()
conn.close()
print('Tüm ürünlerin subcategory alanı JSON listeye dönüştürüldü.')
