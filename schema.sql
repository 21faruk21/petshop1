DROP TABLE IF EXISTS products;

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    image TEXT,
    category TEXT,
    subcategory TEXT,
    description TEXT,
    in_stock INTEGER DEFAULT 1
);
