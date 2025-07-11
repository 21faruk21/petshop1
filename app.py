import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, session, redirect, url_for, request
import sqlite3
import random, string, json
from urllib.parse import quote
from functools import wraps

app = Flask(__name__)
app.secret_key = "supersecretkey"
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}

# Veritabanı yolu - production ortamında farklı konumda olabilir
if os.environ.get('RENDER'):
    # Render.com'da
    db_path = os.path.join(os.getcwd(), "petshop.db")
else:
    # Yerel geliştirme ortamında
    db_path = os.path.join(app.root_path, "instance", "petshop.db")


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
        in_stock INTEGER DEFAULT 1
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
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully!")


# Uygulama başlatıldığında veritabanını oluştur
try:
    init_database()
except Exception as e:
    print(f"Database initialization error: {e}")


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


# ROUTES

@app.route("/")
def index():
    category = request.args.get("category", "")
    subcategory = request.args.get("subcategory", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM products WHERE in_stock = 1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if subcategory:
            query += " AND subcategory = ?"
            params.append(subcategory)
        if min_price:
            query += " AND price >= ?"
            params.append(float(min_price))
        if max_price:
            query += " AND price <= ?"
            params.append(float(max_price))

        cursor.execute(query, params)
        products = cursor.fetchall()
        conn.close()

        return render_template("index.html", products=products)
    except Exception as e:
        print(f"Database error in index: {e}")
        return render_template("index.html", products=[])


@app.route("/products")
def products():
    return redirect(url_for("index"))


@app.route("/contact")
def contact():
    return render_template("contact.html")


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
        category = request.form["category"]
        subcategory = request.form["subcategory"]
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

        # SQL sorgusunu çalıştır
        cursor.execute("""
            UPDATE products
            SET name = ?, price = ?, image = ?, category = ?, subcategory = ?, description = ?
            WHERE id = ?
        """, (name, price, image, category, subcategory, description, product_id))

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
    cart_items = session.get("cart", [])
    total = sum(item["price"] * item.get("quantity", 1) for item in cart_items)

    if not cart_items:
        return redirect(url_for("cart"))

    order_code = "-".join(
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(4)
    )

    # Kullanıcıdan alınan veriler
    customer_name = request.form.get("customer_name", "")
    address = request.form.get("address", "")
    note = request.form.get("note", "")

    # Veritabanına kaydet
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders (order_code, items, total_price, customer_name, address, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (order_code, json.dumps(cart_items), total, customer_name, address, note))
    conn.commit()
    conn.close()

    # WhatsApp yönlendirmesi
    whatsapp_number = "905422192125"
    message = f"""🐾 Merhaba! Siparişimi tamamlamak istiyorum.

Sipariş Kodu: {order_code}
Ad Soyad: {customer_name}
Toplam Tutar: {total} TL

IBAN bilgilerinizi paylaşabilir misiniz?
"""
    whatsapp_link = f"https://wa.me/{whatsapp_number}?text={quote(message)}"

    session.pop("cart", None)
    return redirect(whatsapp_link)


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

    return render_template("admin_orders.html", result=result, items=items, not_found=not_found)


@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        name = request.form["name"]
        price = float(request.form["price"])
        category = request.form["category"]
        subcategory = request.form["subcategory"]
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
            INSERT INTO products (name, price, image, category, subcategory, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, price, image_path, category, subcategory, description))
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


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_panel():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    products = cursor.fetchall()
    conn.close()
    return render_template("admin_panel.html", products=products)


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template("index.html", products=[]), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("index.html", products=[]), 500


if __name__ == "__main__":
    app.run(debug=True)