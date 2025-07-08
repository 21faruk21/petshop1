import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, session, redirect, url_for, request
import sqlite3
import random, string, json
from urllib.parse import quote
from functools import wraps

app = Flask(__name__)
db_path = os.path.join(app.root_path, "instance", "petshop.db")
app.secret_key = "supersecretkey"
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}

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
@app.route("/")
def index():
    category = request.args.get("category", "")
    subcategory = request.args.get("subcategory", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")

    db_path = os.path.join(app.root_path, "instance", "petshop.db")
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
        params.append(min_price)
    if max_price:
        query += " AND price <= ?"
        params.append(max_price)

    cursor.execute(query, params)
    products = cursor.fetchall()
    conn.close()
    return render_template("index.html", products=products)



@app.route("/admin/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    db_path = os.path.join(app.root_path, "instance", "petshop.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        price = float(request.form["price"])
        category = request.form["category"]
        subcategory = request.form["subcategory"]
        description = request.form["description"]
        image = request.form["current_image"]

        # DEBUG: Gelen veriyi kontrol et
        print(f"DEBUG - Description: '{description}'")
        print(f"DEBUG - All form data: {dict(request.form)}")

        # Yeni resim geldiyse güncelle
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                image = f"/static/uploads/{filename}"

        # SQL sorgusunu çalıştır
        cursor.execute("""
            UPDATE products
            SET name = ?, price = ?, image = ?, category = ?, subcategory = ?, description = ?
            WHERE id = ?
        """, (name, price, image, category, subcategory, description, product_id))

        print(f"DEBUG - SQL executed with description: '{description}'")

        conn.commit()
        conn.close()
        return redirect(url_for("admin_panel"))

    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    return render_template("edit_product.html", product=product)

@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    db_path = os.path.join(app.root_path, "instance", "petshop.db")
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
def delete_product(product_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    db_path = os.path.join(app.root_path, "instance", "petshop.db")
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

    import random, string, json
    order_code = "-".join(
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(4)
    )

    # Kullanıcıdan alınan veriler
    customer_name = request.form.get("customer_name", "")
    address = request.form.get("address", "")
    note = request.form.get("note", "")

    # Veritabanına kaydet
    db_path = os.path.join(app.root_path, "instance", "petshop.db")
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
    from urllib.parse import quote
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
def admin_orders():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    result = None
    not_found = False
    items = []

    if request.method == "POST":
        code = request.form["code"].strip().upper()
        db_path = os.path.join(app.root_path, "instance", "petshop.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_code = ?", (code,))
        result = cursor.fetchone()
        conn.close()

        if result:
            try:
                import json
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

        file = request.files["image"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f"/static/uploads/{filename}"
        else:
            image_path = "/static/default.jpg"

        db_path = os.path.join(app.root_path, "instance", "petshop.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (name, price, image, category, subcategory, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, price, image_path, category, subcategory, description))
        conn.commit()
        conn.close()
        return redirect(url_for("add_product"))

    return render_template("add_product.html")

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    db_path = os.path.join(app.root_path, "instance", "petshop.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return "Ürün bulunamadı", 404

    return render_template("product_detail.html", product=product)


    if not row:
        return "Ürün bulunamadı", 404

    product = {
        "id": row[0],
        "name": row[1],
        "price": row[2],
        "image": row[3],
        "category": row[4],
        "subcategory": row[5],
        "description": row[6]
    }
    return render_template("product_detail.html", product=product)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == "adminadmin1admin":
            session["admin_logged_in"] = True
            return redirect("/admin")
        return render_template("admin_login.html", error="Şifre yanlış!")
    return render_template("admin_login.html")

@app.route("/admin")
@login_required
def admin_panel():
    db_path = os.path.join(app.root_path, "instance", "petshop.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    conn.close()
    return render_template("admin_panel.html", products=products)

if __name__ == "__main__":
    app.run(debug=True)
