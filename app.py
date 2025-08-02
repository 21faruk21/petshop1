import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, session, redirect, url_for, request, jsonify, g
from flask_caching import Cache
import sqlite3
import random, string, json
from urllib.parse import quote
from functools import wraps, lru_cache
from markupsafe import Markup
from datetime import datetime
import threading
from contextlib import contextmanager
import time

app = Flask(__name__)
app.secret_key = "supersecretkey"
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes
app.config['TEMPLATES_AUTO_RELOAD'] = False  # Production mode

# Initialize caching
cache = Cache(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}

# Database connection pool
class DatabasePool:
    def __init__(self, db_path, max_connections=10):
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections = []
        self.lock = threading.Lock()
        
    def get_connection(self):
        with self.lock:
            if self.connections:
                return self.connections.pop()
            else:
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                return conn
    
    def return_connection(self, conn):
        with self.lock:
            if len(self.connections) < self.max_connections:
                self.connections.append(conn)
            else:
                conn.close()

# Global database pool
db_pool = None

# Veritabanı yolu - production ortamında farklı konumda olabilir
if os.environ.get('RENDER'):
    # Render.com'da
    db_path = os.path.join(os.getcwd(), "petshop.db")
else:
    # Yerel geliştirme ortamında
    db_path = os.path.join(app.root_path, "instance", "petshop.db")

# Database connection context manager
@contextmanager
def get_db_connection():
    """Context manager for database connections with connection pooling"""
    global db_pool
    if not db_pool:
        db_pool = DatabasePool(db_path)
    
    conn = db_pool.get_connection()
    try:
        yield conn
    finally:
        db_pool.return_connection(conn)


# Veritabanı başlatma fonksiyonu
def init_database():
    # Yerel geliştirme için instance klasörü
    if not os.environ.get('RENDER'):
        instance_dir = os.path.join(app.root_path, "instance")
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir)

    # Upload klasörünü oluştur
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Products tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        image TEXT,
        category TEXT,
        subcategory TEXT,
        description TEXT,
        in_stock INTEGER DEFAULT 1,
        brand TEXT
    )
    """)

    # Orders tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT NOT NULL,
        items TEXT NOT NULL,
        total_price REAL NOT NULL,
        customer_name TEXT,
        address TEXT,
        note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'Hazırlanıyor'
    )
    """)

    # Messages tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        message TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Campaigns tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        image TEXT,
        link TEXT,
        active INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully!")


# Uygulama başlatıldığında veritabanını oluştur
try:
    init_database()
    # Initialize database pool after database is ready
    db_pool = DatabasePool(db_path)
except Exception as e:
    print(f"Database initialization error: {e}")


# --- Migration: Eksik kolonları ekle ---
def migrate_orders_table():
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'Hazırlanıyor'")
        except Exception as e:
            print("status kolonu zaten var veya eklenemedi:", e)
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN shipping_company TEXT")
        except Exception as e:
            print("shipping_company kolonu zaten var veya eklenemedi:", e)
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN tracking_number TEXT")
        except Exception as e:
            print("tracking_number kolonu zaten var veya eklenemedi:", e)
        
        # Products tablosuna brand sütunu ekle
        try:
            cursor.execute("ALTER TABLE products ADD COLUMN brand TEXT")
        except Exception as e:
            print("brand kolonu zaten var veya eklenemedi:", e)
        
        # Orders tablosuna eksik sütunları ekle
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN customer_phone TEXT")
        except Exception as e:
            print("customer_phone kolonu zaten var veya eklenemedi:", e)
        
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN customer_email TEXT")
        except Exception as e:
            print("customer_email kolonu zaten var veya eklenemedi:", e)
        
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN customer_address TEXT")
        except Exception as e:
            print("customer_address kolonu zaten var veya eklenemedi:", e)
        
        conn.commit()
        conn.close()
        print("orders tablosu migration tamamlandı.")
    except Exception as e:
        print("Migration genel hata:", e)

# Sunucu başlarken bir kere çalıştır
migrate_orders_table()


# Decorator for admin login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return decorated_function


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper function for subcategory filtering (optimized)
def filter_products_by_subcategory(products, main_category, subcategory):
    """Optimized subcategory filtering function"""
    filtered_products = []
    for p in products:
        try:
            if isinstance(p, dict):
                subs = json.loads(p.get('subcategory', '[]')) if p.get('subcategory') else []
            else:
                # SQLite Row object
                subs = json.loads(p[5]) if p[5] else []
        except (json.JSONDecodeError, IndexError):
            subs = [p.get('subcategory', '') if isinstance(p, dict) else p[5]] if (p.get('subcategory') if isinstance(p, dict) else p[5]) else []
        
        # Ana kategori filtresi
        if main_category:
            found_main_category = any(main_category.lower() in sub.lower() for sub in subs)
            if not found_main_category:
                continue
        
        # Alt kategori filtresi
        if subcategory and subcategory != "Hepsi":
            if subcategory not in subs:
                continue
        
        # Convert to dict if needed and add subcategory info
        if isinstance(p, dict):
            product_dict = p.copy()
        else:
            product_dict = dict(p)
        product_dict['subcategory'] = subs
        filtered_products.append(product_dict)
        
    return filtered_products

# Performance monitoring decorator
def monitor_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        duration = end_time - start_time
        if duration > 1.0:  # Log slow queries
            print(f"SLOW QUERY: {func.__name__} took {duration:.2f} seconds")
        return result
    return wrapper

# Cached database queries
@cache.memoize(timeout=300)
def get_popular_products(category=None, limit=10):
    """Get popular products based on view/purchase patterns"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM products WHERE in_stock = 1"
        params = []
        
        if category:
            query += " AND LOWER(category) = LOWER(?)"
            params.append(category)
            
        # For now, order by ID desc (newest first) as popularity metric
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

@cache.memoize(timeout=300)
def get_products_by_category(category, brand=None, min_price=None, max_price=None):
    """Cached product retrieval by category"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM products WHERE in_stock = 1 AND LOWER(category) = LOWER(?)"
        params = [category]
        
        if brand:
            query += " AND LOWER(brand) = LOWER(?)"
            params.append(brand)
        if min_price:
            query += " AND price >= ?"
            params.append(float(min_price))
        if max_price:
            query += " AND price <= ?"
            params.append(float(max_price))
            
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

@cache.memoize(timeout=300)
def get_campaigns():
    """Cached campaigns retrieval"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaigns WHERE active = 1")
        return [dict(row) for row in cursor.fetchall()]

@cache.memoize(timeout=60)
def get_product_count_by_category():
    """Cached product count statistics"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM products 
            WHERE in_stock = 1 
            GROUP BY category
        """)
        return dict(cursor.fetchall())


# ROUTES

@app.route("/select_category", methods=["POST"])
def select_category():
    category = request.form.get("category")
    if category:
        session["selected_category"] = category
        return redirect(url_for("index"))
    return redirect(url_for("index"))

@app.route("/change_category")
def change_category():
    session.pop("selected_category", None)
    return redirect(url_for("index"))

@app.route("/")
@monitor_performance
def index():
    # Eğer kullanıcı kategori seçmemişse, kategori seçme ekranı göster
    selected_category = session.get("selected_category")
    if not selected_category:
        return render_template("select_category.html")

    # Kategori seçilmişse, sadece o kategorinin ürünlerini göster
    category = selected_category
    main_category = request.args.get("main_category", "")
    subcategory = request.args.get("subcategory", "")
    brand = request.args.get("brand", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")

    try:
        # Use cached campaign data
        campaigns = get_campaigns()
        
        # Use cached product data with filters
        products = get_products_by_category(category, brand, min_price, max_price)

        # Çoklu subcategory desteği: filtreleme (optimized)
        filtered_products = filter_products_by_subcategory(products, main_category, subcategory)
            
        return render_template("index.html", products=filtered_products, selected_category=category, campaigns=campaigns)
    except Exception as e:
        print(f"Database error in index: {e}")
        return render_template("index.html", products=[], selected_category=category, campaigns=[])


@app.route("/products")
def products():
    return redirect(url_for("index"))

@app.route("/api/search")
@monitor_performance
def search_products():
    """Real-time product search API"""
    query = request.args.get('q', '').strip()
    category = session.get("selected_category")
    
    if not query or len(query) < 2:
        return jsonify({"products": [], "suggestions": []})
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Search in product names, brands, and descriptions
            search_query = """
                SELECT * FROM products 
                WHERE in_stock = 1 
                AND (LOWER(name) LIKE ? OR LOWER(brand) LIKE ? OR LOWER(description) LIKE ?)
            """
            
            if category:
                search_query += " AND LOWER(category) = LOWER(?)"
                params = [f"%{query.lower()}%", f"%{query.lower()}%", f"%{query.lower()}%", category]
            else:
                params = [f"%{query.lower()}%", f"%{query.lower()}%", f"%{query.lower()}%"]
            
            cursor.execute(search_query, params)
            products = [dict(row) for row in cursor.fetchall()]
            
            # Generate search suggestions
            suggestions = list(set([p['name'] for p in products[:5]]))
            
            return jsonify({
                "products": products[:20],  # Limit to 20 results
                "suggestions": suggestions,
                "count": len(products)
            })
            
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/filter_products")
@monitor_performance
def filter_products():
    """AJAX için dinamik ürün filtreleme endpoint'i (optimized)"""
    selected_category = session.get("selected_category")
    if not selected_category:
        return jsonify({"error": "Kategori seçilmemiş"}), 400

    category = selected_category
    main_category = request.args.get("main_category", "")
    subcategory = request.args.get("subcategory", "")
    brand = request.args.get("brand", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")

    try:
        # Use cached product data
        products = get_products_by_category(category, brand, min_price, max_price)
        
        # Apply subcategory filtering
        filtered_products = filter_products_by_subcategory(products, main_category, subcategory)
        
        # Convert to JSON format
        json_products = []
        for p in filtered_products:
            product_dict = {
                "id": p["id"],
                "name": p["name"],
                "price": p["price"],
                "image": p["image"],
                "category": p["category"],
                "subcategory": p.get("subcategory", []),
                "brand": p.get("brand", ""),
                "description": p.get("description", "")
            }
            json_products.append(product_dict)
            
        return jsonify({"products": json_products, "count": len(json_products)})
    except Exception as e:
        print(f"Database error in filter_products: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/contact", methods=["GET", "POST"])
def contact():
    message = None
    if request.method == "POST":
        name = request.form.get("name", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        msg = request.form.get("message", "")
        if name and email and msg:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages (name, email, phone, message) VALUES (?, ?, ?, ?)", (name, email, phone, msg))
            conn.commit()
            conn.close()
            message = "Mesajınız başarıyla gönderildi!"
        else:
            message = "Lütfen zorunlu alanları doldurun."
    return render_template("contact.html", message=message)


@app.route("/thank_you")
def thank_you():
    return render_template("thank_you.html")


@app.route("/admin/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        price = float(request.form["price"])
        category = request.form["category"]  # Hayvan türü
        main_category = request.form.get("main_category", "")  # Ana kategori
        brand = request.form.get("brand", "")
        subcategory = request.form.getlist("subcategory")
        if not subcategory:
            subcategory = []
        
        # Ana kategori bilgisini de subcategory listesine dahil et
        if main_category and main_category not in subcategory:
            subcategory.insert(0, main_category)
        
        subcategory_json = json.dumps(subcategory, ensure_ascii=False)
        description = request.form["description"]

        # Mevcut resim bilgisini al
        cursor.execute("SELECT image FROM products WHERE id = ?", (product_id,))
        current_product = cursor.fetchone()
        image = current_product[0] if current_product else "/static/default.jpg"

        # Yeni resim geldiyse güncelle
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                image = f"/static/uploads/{filename}"

        cursor.execute("""
            UPDATE products
            SET name = ?, price = ?, image = ?, category = ?, subcategory = ?, description = ?, brand = ?
            WHERE id = ?
        """, (name, price, image, category, subcategory_json, description, brand, product_id))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_panel"))

    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return "Ürün bulunamadı", 404

    return render_template("edit_product.html", product=product)


@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return "Ürün bulunamadı", 404

    item = {"id": product[0], "name": product[1], "price": product[2], "quantity": 1}

    if "cart" not in session:
        session["cart"] = []

    # Sepette aynı ürün varsa miktarını artır
    for cart_item in session["cart"]:
        if cart_item["id"] == item["id"]:
            cart_item["quantity"] += 1
            break
    else:
        session["cart"].append(item)

    session.modified = True
    return redirect(url_for("index"))


@app.route("/cart")
def cart():
    cart_items = session.get("cart", [])
    total = sum(item["price"] * item.get("quantity", 1) for item in cart_items)
    return render_template("cart.html", cart_items=cart_items, total=total)


@app.route("/admin/delete/<int:product_id>")
@login_required
def delete_product(product_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


@app.route("/clear_cart")
def clear_cart():
    session["cart"] = []
    return redirect(url_for("cart"))


@app.route("/toggle_theme", methods=["POST"])
def toggle_theme():
    current = session.get("theme", "light")
    session["theme"] = "dark" if current == "light" else "light"
    return redirect(request.referrer or url_for("index"))


@app.context_processor
def inject_theme():
    return dict(theme=session.get("theme", "light"))


@app.route("/remove_from_cart/<int:index>")
def remove_from_cart(index):
    if "cart" in session:
        try:
            session["cart"].pop(index)
            session.modified = True
        except IndexError:
            pass
    return redirect(url_for("cart"))


@app.route("/order", methods=["POST"])
def order():
    try:
        cart_items = session.get("cart", [])
        total = sum(item["price"] * item.get("quantity", 1) for item in cart_items)

        if not cart_items:
            return redirect(url_for("cart"))

        order_code = "-".join(
            ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(4)
        )

        # Kullanıcıdan alınan veriler
        customer_name = request.form.get("customer_name", "")
        phone = request.form.get("phone", "")
        email = request.form.get("email", "")
        address = request.form.get("address", "")
        note = request.form.get("note", "")

        # Veritabanına kaydet
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (order_code, items, total_price, customer_name, customer_phone, customer_email, customer_address, address, note, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_code, json.dumps(cart_items), total, customer_name, phone, email, address, address, note, 'Hazırlanıyor'))
        conn.commit()
        conn.close()

        # WhatsApp yönlendirmesi
        whatsapp_number = "905422192125"
        message = f"""🐾 Merhaba! Siparişimi tamamlamak istiyorum.\n\nSipariş Kodu: {order_code}\nAd Soyad: {customer_name}\nToplam Tutar: {total} TL\n\nIBAN bilgilerinizi paylaşabilir misiniz?\n"""
        whatsapp_link = f"https://wa.me/{whatsapp_number}?text={quote(message)}"

        session.pop("cart", None)
        return redirect(whatsapp_link)
    except Exception as e:
        print(f"ORDER ERROR: {e}")
        return f"Bir hata oluştu: {e}", 500


@app.route("/update_quantity/<int:index>", methods=["POST"])
def update_quantity(index):
    if "cart" in session:
        try:
            quantity = int(request.form["quantity"])
            if quantity < 1:
                quantity = 1
            session["cart"][index]["quantity"] = quantity
            session.modified = True
        except (IndexError, ValueError):
            pass
    return redirect(url_for("cart"))


@app.route("/admin/orders", methods=["GET", "POST"])
@login_required
def admin_orders():
    result = None
    not_found = False
    items = []
    all_orders = []

    # Tüm siparişleri her durumda getir
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cursor.fetchall()
    
    # Siparişleri formatla
    for order in orders:
        order_dict = dict(order)
        try:
            order_dict["items"] = json.loads(order["items"])
        except:
            order_dict["items"] = []
        
        # created_at'i datetime object'e çevir
        try:
            if order_dict["created_at"]:
                order_dict["created_at"] = datetime.strptime(order_dict["created_at"], "%Y-%m-%d %H:%M:%S")
        except:
            order_dict["created_at"] = datetime.now()
        
        all_orders.append(order_dict)
    
    # Spesifik sipariş arama
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        cursor.execute("SELECT * FROM orders WHERE order_code = ?", (code,))
        result = cursor.fetchone()

        if result:
            try:
                items = json.loads(result["items"])
            except:
                items = []
            
            # created_at'i datetime object'e çevir
            result = dict(result)
            try:
                if result["created_at"]:
                    result["created_at"] = datetime.strptime(result["created_at"], "%Y-%m-%d %H:%M:%S")
            except:
                result["created_at"] = datetime.now()
        else:
            not_found = True

    conn.close()
    return render_template("admin_orders.html", result=result, items=items, not_found=not_found, all_orders=all_orders)


@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        name = request.form["name"]
        price = float(request.form["price"])
        category = request.form["category"]  # Hayvan türü
        main_category = request.form.get("main_category", "")  # Ana kategori (Mama, Aksesuar, vb.)
        brand = request.form.get("brand", "")
        # Çoklu seçim desteği: subcategory birden fazla ise liste olarak gelir
        subcategory = request.form.getlist("subcategory")
        if not subcategory:
            subcategory = []
        
        # Ana kategori bilgisini de subcategory listesine dahil et
        if main_category and main_category not in subcategory:
            subcategory.insert(0, main_category)
        
        # JSON string olarak kaydet
        subcategory_json = json.dumps(subcategory, ensure_ascii=False)
        description = request.form["description"]

        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f"/static/uploads/{filename}"
        else:
            image_path = "/static/default.jpg"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (name, price, image, category, subcategory, description, brand)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, price, image_path, category, subcategory_json, description, brand))
        conn.commit()
        conn.close()
        return redirect(url_for("admin_panel"))

    return render_template("add_product.html")


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return "Ürün bulunamadı", 404

    return render_template("product_detail.html", product=product)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == "adminadmin1admin":
            session["admin_logged_in"] = True
            return redirect(url_for("admin_panel"))
        return render_template("admin_login.html", error="Şifre yanlış!")
    return render_template("admin_login.html")


@app.route("/admin/update_order_status", methods=["POST"])
@login_required
def update_order_status_api():
    try:
        data = request.get_json()
        order_id = data.get("order_id")
        new_status = data.get("status")
        
        if not order_id or not new_status:
            return jsonify({"success": False, "message": "Eksik parametreler"}), 400
        
        # Geçerli durumlar
        valid_statuses = ["Hazırlanıyor", "Kargoda", "Teslim Edildi", "İptal Edildi"]
        if new_status not in valid_statuses:
            return jsonify({"success": False, "message": "Geçersiz durum"}), 400
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Sipariş var mı kontrol et
        cursor.execute("SELECT id FROM orders WHERE id = ?", (order_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "message": "Sipariş bulunamadı"}), 404
        
        # Durumu güncelle
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Sipariş durumu güncellendi"})
    
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/admin/update_shipping_info", methods=["POST"])
@login_required
def update_shipping_info():
    try:
        data = request.get_json()
        order_id = data.get("order_id")
        field = data.get("field")
        value = data.get("value")
        
        if not order_id or not field:
            return jsonify({"success": False, "message": "Eksik parametreler"}), 400
        
        # Güvenlik kontrolü - sadece belirli alanlar güncellenebilir
        allowed_fields = ["shipping_company", "tracking_number"]
        if field not in allowed_fields:
            return jsonify({"success": False, "message": "Geçersiz alan"}), 400
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Sipariş var mı kontrol et
        cursor.execute("SELECT id FROM orders WHERE id = ?", (order_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "message": "Sipariş bulunamadı"}), 404
        
        # Bilgiyi güncelle
        cursor.execute(f"UPDATE orders SET {field} = ? WHERE id = ?", (value, order_id))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Kargo bilgisi güncellendi"})
    
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))


@app.route("/admin")
@app.route("/admin/")
@login_required
def admin_panel():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Ürünleri al
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    products = cursor.fetchall()
    
    # Siparişleri al
    cursor.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cursor.fetchall()
    
    # Her siparişi dict'e çevirip ürünlerini ekle
    orders_with_items = []
    for order in orders:
        order_dict = dict(order)
        try:
            order_dict["items"] = json.loads(order["items"])
        except:
            order_dict["items"] = []
        
        # created_at'i datetime object'e çevir
        try:
            if order_dict["created_at"]:
                order_dict["created_at"] = datetime.strptime(order_dict["created_at"], "%Y-%m-%d %H:%M:%S")
        except:
            # Eğer datetime dönüşümü başarısız olursa şu anki zamanı kullan
            order_dict["created_at"] = datetime.now()
        
        orders_with_items.append(order_dict)
    
    # İstatistikler için sayıları hesapla
    cursor.execute("SELECT COUNT(*) as count FROM products")
    product_count = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM orders")
    order_count = cursor.fetchone()["count"]
    
    # Mesaj tablosu varsa mesaj sayısını al
    try:
        cursor.execute("SELECT COUNT(*) as count FROM messages")
        message_count = cursor.fetchone()["count"]
    except:
        message_count = 0
    
    # Kampanya tablosu varsa kampanya sayısını al
    try:
        cursor.execute("SELECT COUNT(*) as count FROM campaigns")
        campaign_count = cursor.fetchone()["count"]
    except:
        campaign_count = 0
    
    # Son 5 siparişi al
    recent_orders = orders_with_items[:5]
    
    conn.close()
    return render_template("admin_panel.html", 
                         products=products, 
                         orders=orders_with_items,
                         product_count=product_count,
                         order_count=order_count,
                         message_count=message_count,
                         campaign_count=campaign_count,
                         recent_orders=recent_orders)


@app.route("/admin/campaigns", methods=["GET", "POST"])
@login_required
def admin_campaigns():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    message = None
    
    # Kampanya ekleme
    if request.method == "POST":
        title = request.form.get("title", "")
        link = request.form.get("link", "")
        description = request.form.get("description", "")
        active = 1 if request.form.get("active") == "on" else 0
        file = request.files.get("image")
        
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f"/static/uploads/{filename}"
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # description kolonu yoksa ekle
            try:
                cursor.execute("ALTER TABLE campaigns ADD COLUMN description TEXT")
                conn.commit()
            except:
                pass
            
            cursor.execute("INSERT INTO campaigns (image, link, title, description, active, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
                         (image_path, link, title, description, active, created_at))
            conn.commit()
            message = "Kampanya başarıyla eklendi!"
        else:
            message = "Lütfen geçerli bir görsel dosyası seçin."
    
    # Kampanya silme
    if request.args.get("delete"):
        cid = request.args.get("delete")
        try:
            cursor.execute("DELETE FROM campaigns WHERE id = ?", (cid,))
            conn.commit()
            message = "Kampanya başarıyla silindi!"
        except Exception as e:
            message = f"Kampanya silinirken hata oluştu: {str(e)}"
    
    # Aktif/pasif yapma
    if request.args.get("toggle"):
        cid = request.args.get("toggle")
        try:
            cursor.execute("SELECT active FROM campaigns WHERE id = ?", (cid,))
            row = cursor.fetchone()
            if row:
                new_status = 0 if row[0] else 1
                cursor.execute("UPDATE campaigns SET active = ? WHERE id = ?", (new_status, cid))
                conn.commit()
                status_text = "aktif" if new_status else "pasif"
                message = f"Kampanya durumu {status_text} yapıldı!"
        except Exception as e:
            message = f"Kampanya durumu güncellenirken hata oluştu: {str(e)}"
    
    # Kampanyaları getir
    cursor.execute("SELECT * FROM campaigns ORDER BY id DESC")
    campaigns_raw = cursor.fetchall()
    conn.close()
    
    # Campaigns'ı formatla
    campaigns = []
    for campaign in campaigns_raw:
        campaign_dict = dict(campaign)
        # created_at'i datetime object'e çevir - güvenli şekilde
        try:
            if campaign_dict.get("created_at"):
                campaign_dict["created_at"] = datetime.strptime(campaign_dict["created_at"], "%Y-%m-%d %H:%M:%S")
            else:
                campaign_dict["created_at"] = datetime.now()
        except:
            campaign_dict["created_at"] = datetime.now()
        
        # description alanını kontrol et
        if "description" not in campaign_dict:
            campaign_dict["description"] = ""
        
        campaigns.append(campaign_dict)
    
    return render_template("admin_campaigns.html", campaigns=campaigns, message=message)


@app.route("/admin/messages")
@login_required
def admin_messages():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages ORDER BY created_at DESC")
    messages_raw = cursor.fetchall()
    conn.close()
    
    # Messages'ı formatla
    messages = []
    for message in messages_raw:
        message_dict = dict(message)
        # created_at'i datetime object'e çevir
        try:
            if message_dict["created_at"]:
                message_dict["created_at"] = datetime.strptime(message_dict["created_at"], "%Y-%m-%d %H:%M:%S")
        except:
            message_dict["created_at"] = datetime.now()
        messages.append(message_dict)
    
    return render_template("admin_messages.html", messages=messages)


@app.route("/admin/update_order_status/<int:order_id>", methods=["POST"], endpoint="update_order_status_form")
@login_required  
def update_order_status_form(order_id):
    new_status = request.form.get("status", "Hazırlanıyor")
    shipping_company = request.form.get("shipping_company", "")
    tracking_number = request.form.get("tracking_number", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ?, shipping_company = ?, tracking_number = ? WHERE id = ?", (new_status, shipping_company, tracking_number, order_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


@app.route("/order-track", methods=["GET", "POST"])
def order_track():
    result = None
    not_found = False
    items = []
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_code = ?", (code,))
        result = cursor.fetchone()
        conn.close()
        if result:
            try:
                items = json.loads(result["items"])
            except:
                items = []
        else:
            not_found = True
    return render_template("order_track.html", result=result, items=items, not_found=not_found)


@app.route("/api/suggestions")
@monitor_performance 
def get_suggestions():
    """Get search suggestions for autocomplete"""
    query = request.args.get('q', '').strip()
    category = session.get("selected_category")
    
    if not query or len(query) < 2:
        return jsonify({"suggestions": []})
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get unique product names and brands for suggestions
            suggestion_query = """
                SELECT DISTINCT name, brand FROM products 
                WHERE in_stock = 1 
                AND (LOWER(name) LIKE ? OR LOWER(brand) LIKE ?)
            """
            
            if category:
                suggestion_query += " AND LOWER(category) = LOWER(?)"
                params = [f"%{query.lower()}%", f"%{query.lower()}%", category]
            else:
                params = [f"%{query.lower()}%", f"%{query.lower()}%"]
            
            cursor.execute(suggestion_query + " LIMIT 10", params)
            results = cursor.fetchall()
            
            suggestions = []
            for row in results:
                if row['name'] and query.lower() in row['name'].lower():
                    suggestions.append(row['name'])
                if row['brand'] and query.lower() in row['brand'].lower():
                    suggestions.append(row['brand'])
            
            # Remove duplicates and limit to 8 suggestions
            suggestions = list(set(suggestions))[:8]
            
            return jsonify({"suggestions": suggestions})
            
    except Exception as e:
        print(f"Suggestions error: {e}")
        return jsonify({"suggestions": []})


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template("index.html", products=[]), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("index.html", products=[]), 500


@app.template_filter('fromjson')
def fromjson_filter(s):
    return json.loads(s)


def escapejs_filter(value):
    return Markup(json.dumps(str(value)))

app.jinja_env.filters['escapejs'] = escapejs_filter

if __name__ == "__main__":
    app.run(debug=True)