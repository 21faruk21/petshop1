import os
import secrets
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, session, redirect, url_for, request, jsonify, g
from flask_caching import Cache
import sqlite3
import random, string, json
from urllib.parse import quote
from functools import wraps, lru_cache
from markupsafe import Markup
from datetime import datetime, timedelta
import threading
from contextlib import contextmanager
import time
import hashlib
from collections import defaultdict
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import uuid
import traceback
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
# Generate secure secret key or use environment variable
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 1800  # 30 minutes (improved from 5)
app.config['CACHE_THRESHOLD'] = 500  # Max cached items
app.config['TEMPLATES_AUTO_RELOAD'] = False  # Production mode

# Initialize caching
cache = Cache(app)

# Enhanced logging configuration
logging.basicConfig(level=logging.INFO)

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure file handler for application logs
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

# Configure error handler
error_handler = RotatingFileHandler('logs/errors.log', maxBytes=10240000, backupCount=10)
error_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
error_handler.setLevel(logging.ERROR)
app.logger.addHandler(error_handler)

app.logger.setLevel(logging.INFO)
app.logger.info('Mavi Petshop startup')

# Cache invalidation helper functions
def invalidate_product_cache(category=None):
    """Invalidate product-related cache entries"""
    cache.delete_memoized(get_popular_products)
    cache.delete_memoized(get_product_count_by_category)
    if category:
        cache.delete_memoized(get_products_by_category, category)
    else:
        # Clear all category caches (more comprehensive but less efficient)
        cache.clear()
    print(f"Product cache invalidated for category: {category or 'all'}")

def invalidate_campaign_cache():
    """Invalidate campaigns cache"""
    cache.delete_memoized(get_campaigns)
    print("Campaign cache invalidated")

def invalidate_brand_cache():
    """Invalidate brands cache"""
    cache.delete_memoized(get_brands)
    print("Brand cache invalidated")

# Rate limiting system
rate_limit_storage = defaultdict(list)
RATE_LIMIT_REQUESTS = 60  # Max requests per minute
RATE_LIMIT_WINDOW = 60   # Time window in seconds

def get_client_ip():
    """Get client IP address"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def rate_limit_check(max_requests=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW):
    """Check if client has exceeded rate limit"""
    client_ip = get_client_ip()
    now = datetime.now()
    
    # Clean old entries
    cutoff_time = now - timedelta(seconds=window)
    rate_limit_storage[client_ip] = [
        timestamp for timestamp in rate_limit_storage[client_ip] 
        if timestamp > cutoff_time
    ]
    
    # Check if rate limit exceeded
    if len(rate_limit_storage[client_ip]) >= max_requests:
        return False
    
    # Add current request
    rate_limit_storage[client_ip].append(now)
    return True

def rate_limit(max_requests=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW):
    """Rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not rate_limit_check(max_requests, window):
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {max_requests} requests per {window} seconds"
                }), 429
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Input validation helpers
def validate_price(price_str):
    """Validate price input"""
    try:
        price = float(price_str)
        return 0 <= price <= 999999  # Reasonable price range
    except (ValueError, TypeError):
        return False

def validate_text_input(text, max_length=500, min_length=1):
    """Validate text input"""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    return min_length <= len(text) <= max_length

def sanitize_filename(filename):
    """Enhanced filename sanitization"""
    if not filename:
        return None
    filename = secure_filename(filename)
    # Additional sanitization
    filename = filename.replace('..', '').replace('/', '').replace('\\', '')
    return filename[:100]  # Limit filename length

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}

# Enhanced Database connection pool
class DatabasePool:
    def __init__(self, db_path, max_connections=20):  # Increased pool size
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections = []
        self.in_use = set()  # Track connections in use
        self.lock = threading.Lock()
        self.created_count = 0
        
    def get_connection(self):
        with self.lock:
            if self.connections:
                conn = self.connections.pop()
                self.in_use.add(id(conn))
                return conn
            elif self.created_count < self.max_connections:
                conn = sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=30.0,  # 30 second timeout
                    isolation_level=None  # Autocommit mode for better performance
                )
                conn.row_factory = sqlite3.Row
                # Enable WAL mode for better concurrency
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')  # Better performance
                conn.execute('PRAGMA temp_store=MEMORY')   # Use memory for temp tables
                conn.execute('PRAGMA mmap_size=268435456')  # 256MB memory map
                self.created_count += 1
                self.in_use.add(id(conn))
                return conn
            else:
                # Pool exhausted, create temporary connection
                conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
                conn.row_factory = sqlite3.Row
                return conn
    
    def return_connection(self, conn):
        with self.lock:
            conn_id = id(conn)
            if conn_id in self.in_use:
                self.in_use.remove(conn_id)
                if len(self.connections) < self.max_connections:
                    # Test connection health before returning to pool
                    try:
                        conn.execute('SELECT 1').fetchone()
                        self.connections.append(conn)
                    except:
                        conn.close()
                        self.created_count -= 1
                else:
                    conn.close()
            else:
                # Temporary connection, just close it
                conn.close()
    
    def get_stats(self):
        """Get pool statistics for monitoring"""
        with self.lock:
            return {
                'available': len(self.connections),
                'in_use': len(self.in_use),
                'total_created': self.created_count,
                'max_connections': self.max_connections
            }

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

    # Users tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME,
        email_verified INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )
    """)

    # Wishlist tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wishlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (product_id) REFERENCES products (id),
        UNIQUE(user_id, product_id)
    )
    """)

    # Reviews tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
        title TEXT,
        comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_verified INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    """)

    # Newsletter subscriptions tablosunu oluştur
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        unsubscribed_at DATETIME
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

    # Create performance-enhancing indexes
    try:
        # Products table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON products(price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_in_stock ON products(in_stock)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category_brand ON products(category, brand)")
        
        # Orders table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_code ON orders(order_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_email ON orders(customer_email)")
        
        # Messages table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_email ON messages(email)")
        
        # Campaigns table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_active ON campaigns(active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON campaigns(created_at)")
        
        print("Database indexes created successfully!")
    except Exception as e:
        print(f"Index creation error: {e}")

    # Add sample products if database is empty
    cursor.execute("SELECT COUNT(*) FROM products")
    product_count = cursor.fetchone()[0]
    
    if product_count == 0:
        print("🌱 Adding sample products...")
        sample_products = [
            ("Royal Canin Kitten Mama", 450.0, "/static/uploads/1.webp", "Kedi", '["Mama"]', "2-12 aylık yavrular için özel formül kedi maması", "Royal Canin"),
            ("Lavital Kitten Somonlu Yavru Kedi Maması 1.5 KG", 340.0, "/static/uploads/2.webp", "Kedi", '["Mama"]', "6-52 hafta - 12 aylık dönemdeki yavru kediler için özel formüle edilen bir yavru kedi mamasıdır.", "Lavital"),
            ("Whiskas Yetişkin Kedi Maması", 280.0, "/static/uploads/3.webp", "Kedi", '["Mama"]', "Yetişkin kediler için dengeli beslenme", "Whiskas"),
            ("Pro Plan Köpek Maması", 520.0, "/static/uploads/4.webp", "Köpek", '["Mama"]', "Yetişkin köpekler için premium mama", "Pro Plan"),
            ("Pedigree Köpek Maması", 380.0, "/static/uploads/5.webp", "Köpek", '["Mama"]', "Köpeklerin sağlıklı yaşamı için", "Pedigree"),
            ("Kedi Oyuncağı Top", 45.0, "/static/uploads/6.webp", "Kedi", '["Oyuncak"]', "Renkli kedi oyun topu", "Generic"),
            ("Köpek Tasması", 120.0, "/static/uploads/7.webp", "Köpek", '["Aksesuar"]', "Ayarlanabilir köpek tasması", "Generic"),
            ("Kedi Kumu 10L", 85.0, "/static/uploads/8.webp", "Kedi", '["Bakım"]', "Kokusuz kedi kumu", "Generic"),
            ("Balık Yemi", 25.0, "/static/uploads/9.webp", "Balık", '["Yem"]', "Tropikal balıklar için yem", "Generic"),
            ("Kuş Yemi", 35.0, "/static/uploads/10.webp", "Kuş", '["Yem"]', "Muhabbet kuşları için karma yem", "Generic"),
        ]
        
        for product in sample_products:
            cursor.execute("""
                INSERT INTO products (name, price, image, category, subcategory, description, brand, in_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, product)
        
        print(f"✅ {len(sample_products)} sample products added!")
    else:
        print(f"📦 Database already has {product_count} products")

    conn.commit()
    conn.close()
    print("Database initialized successfully!")


# Uygulama başlatıldığında veritabanını oluştur
print(f"🚀 Mavi Petshop startup")
print(f"🗄️ Database path: {db_path}")
print(f"📁 Database exists before init: {os.path.exists(db_path)}")

try:
    init_database()
    print(f"✅ Database initialized successfully!")
    print(f"📁 Database exists after init: {os.path.exists(db_path)}")
    
    # Initialize database pool after database is ready
    db_pool = DatabasePool(db_path)
    print(f"🏊 Database pool initialized")
except Exception as e:
    print(f"💥 Database initialization error: {e}")
    import traceback
    print(f"📋 Full init traceback: {traceback.format_exc()}")


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
        
        # Add stock quantity column for enhanced inventory management
        try:
            cursor.execute("ALTER TABLE products ADD COLUMN stock_quantity INTEGER DEFAULT 10")
        except Exception as e:
            print("stock_quantity kolonu zaten var veya eklenemedi:", e)
        
        # Add low_stock_threshold column
        try:
            cursor.execute("ALTER TABLE products ADD COLUMN low_stock_threshold INTEGER DEFAULT 5")
        except Exception as e:
            print("low_stock_threshold kolonu zaten var veya eklenemedi:", e)
        
        # Add stock tracking columns
        try:
            cursor.execute("ALTER TABLE products ADD COLUMN last_restocked DATETIME")
        except Exception as e:
            print("last_restocked kolonu zaten var veya eklenemedi:", e)
        
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
@cache.memoize(timeout=3600)  # 1 hour - products don't change often
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

@cache.memoize(timeout=1800)  # 30 minutes - balanced for product updates
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

@cache.memoize(timeout=600)  # 10 minutes - campaigns change more frequently
def get_campaigns():
    """Cached campaigns retrieval"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaigns WHERE active = 1")
        return [dict(row) for row in cursor.fetchall()]

@cache.memoize(timeout=1800)  # 30 minutes - stats don't change often
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

@cache.memoize(timeout=300)  # 5 minutes - stock changes frequently
def get_low_stock_products(threshold=5):
    """Get products with low stock"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, category, brand, stock_quantity, low_stock_threshold, price
            FROM products 
            WHERE in_stock = 1 
            AND stock_quantity <= COALESCE(low_stock_threshold, ?)
            ORDER BY stock_quantity ASC
        """, (threshold,))
        return [dict(row) for row in cursor.fetchall()]

@cache.memoize(timeout=600)  # 10 minutes
def get_stock_statistics():
    """Get overall stock statistics"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Total products and stock value
        cursor.execute("""
            SELECT 
                COUNT(*) as total_products,
                SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as active_products,
                SUM(CASE WHEN in_stock = 1 THEN COALESCE(stock_quantity, 0) ELSE 0 END) as total_stock_units,
                SUM(CASE WHEN in_stock = 1 THEN COALESCE(stock_quantity, 0) * price ELSE 0 END) as total_stock_value,
                COUNT(CASE WHEN stock_quantity <= COALESCE(low_stock_threshold, 5) AND in_stock = 1 THEN 1 END) as low_stock_count
            FROM products
        """)
        
        return dict(cursor.fetchone())

def update_product_stock(product_id, quantity_change, reason="manual"):
    """Update product stock with logging"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get current stock
        cursor.execute("SELECT stock_quantity, name FROM products WHERE id = ?", (product_id,))
        result = cursor.fetchone()
        
        if not result:
            return False
        
        current_stock = result['stock_quantity'] or 0
        new_stock = max(0, current_stock + quantity_change)
        
        # Update stock
        cursor.execute("""
            UPDATE products 
            SET stock_quantity = ?, 
                last_restocked = CASE WHEN ? > 0 THEN CURRENT_TIMESTAMP ELSE last_restocked END
            WHERE id = ?
        """, (new_stock, quantity_change, product_id))
        
        conn.commit()
        
        # Invalidate stock-related caches
        invalidate_product_cache()
        cache.delete_memoized(get_low_stock_products)
        cache.delete_memoized(get_stock_statistics)
        
        print(f"Stock updated for {result['name']}: {current_stock} -> {new_stock} ({reason})")
        return True

# Customer Communication System
class NotificationService:
    def __init__(self):
        self.email_enabled = bool(os.environ.get('SMTP_SERVER'))
        self.sms_enabled = bool(os.environ.get('SMS_API_KEY'))
        
        # Email configuration
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.email_user = os.environ.get('EMAIL_USER', '')
        self.email_password = os.environ.get('EMAIL_PASSWORD', '')
        self.email_from = os.environ.get('EMAIL_FROM', 'noreply@mavipetshop.com')
        
        # SMS configuration (placeholder for external service)
        self.sms_api_key = os.environ.get('SMS_API_KEY', '')
        self.sms_sender = os.environ.get('SMS_SENDER', 'MaviPetshop')
    
    def send_email(self, to_email, subject, body, html_body=None):
        """Send email notification"""
        if not self.email_enabled or not to_email:
            print(f"Email not sent - Enabled: {self.email_enabled}, To: {to_email}")
            return False
            
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_from
            msg['To'] = to_email
            
            # Text version
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # HTML version if provided
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            print(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            print(f"Email sending failed: {e}")
            return False
    
    def send_sms(self, phone_number, message):
        """Send SMS notification (placeholder for external SMS service)"""
        if not self.sms_enabled or not phone_number:
            print(f"SMS not sent - Enabled: {self.sms_enabled}, Phone: {phone_number}")
            return False
        
        # This is a placeholder - integrate with actual SMS service like Twilio, Netgsm, etc.
        print(f"SMS would be sent to {phone_number}: {message}")
        return True
    
    def notify_order_status_change(self, order_data, new_status):
        """Send notification when order status changes"""
        customer_email = order_data.get('customer_email')
        customer_phone = order_data.get('customer_phone')
        order_code = order_data.get('order_code')
        customer_name = order_data.get('customer_name', 'Değerli Müşteri')
        
        # Email notification
        if customer_email:
            subject = f"Sipariş Durumu Güncellendi - {order_code}"
            body = f"""
Merhaba {customer_name},

Sipariş kodunuz: {order_code}
Yeni durum: {new_status}

Siparişinizi takip etmek için: https://mavipetshop.com/order-track

Teşekkürler,
Mavi Petshop Ekibi
            """
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
        <h1 style="color: white; margin: 0;">🐾 Mavi Petshop</h1>
    </div>
    <div style="padding: 20px; background: #f8f9fa;">
        <h2 style="color: #333;">Merhaba {customer_name},</h2>
        <p>Siparişinizin durumu güncellendi:</p>
        <div style="background: white; border-radius: 10px; padding: 15px; margin: 20px 0; border-left: 4px solid #667eea;">
            <p><strong>Sipariş Kodu:</strong> {order_code}</p>
            <p><strong>Yeni Durum:</strong> <span style="color: #28a745; font-weight: bold;">{new_status}</span></p>
        </div>
        <div style="text-align: center; margin: 30px 0;">
            <a href="https://mavipetshop.com/order-track" 
               style="background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                Siparişimi Takip Et
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            Bu otomatik bir bildirimdir. Sorularınız için bizimle iletişime geçebilirsiniz.
        </p>
    </div>
</body>
</html>
            """
            
            self.send_email(customer_email, subject, body, html_body)
        
        # SMS notification
        if customer_phone:
            sms_message = f"🐾 Mavi Petshop: Sipariş {order_code} durumu '{new_status}' olarak güncellendi. Takip: mavipetshop.com/order-track"
            self.send_sms(customer_phone, sms_message)
    
    def notify_low_stock(self, product_name, current_stock, threshold):
        """Notify admin about low stock"""
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@mavipetshop.com')
        
        subject = f"🚨 Düşük Stok Uyarısı - {product_name}"
        body = f"""
DÜŞÜK STOK UYARISI

Ürün: {product_name}
Mevcut Stok: {current_stock}
Eşik: {threshold}

Lütfen stok ekleyin: https://mavipetshop.com/admin/stock

Mavi Petshop Sistem
        """
        
        self.send_email(admin_email, subject, body)

# Initialize notification service
notification_service = NotificationService()

# User Management System
class UserManager:
    @staticmethod
    def validate_email(email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password(password):
        """Validate password strength"""
        if len(password) < 8:
            return False, "Şifre en az 8 karakter olmalıdır"
        if not re.search(r'[A-Za-z]', password):
            return False, "Şifre en az bir harf içermelidir"
        if not re.search(r'\d', password):
            return False, "Şifre en az bir rakam içermelidir"
        return True, "Geçerli şifre"
    
    @staticmethod
    def create_user(email, password, first_name, last_name, phone=None, address=None):
        """Create a new user account"""
        try:
            # Validate input
            if not UserManager.validate_email(email):
                return False, "Geçersiz email formatı"
            
            is_valid, message = UserManager.validate_password(password)
            if not is_valid:
                return False, message
            
            if not first_name or not last_name:
                return False, "Ad ve soyad zorunludur"
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Check if user already exists
                cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower(),))
                if cursor.fetchone():
                    return False, "Bu email adresi zaten kullanılmaktadır"
                
                # Create user
                password_hash = generate_password_hash(password)
                cursor.execute("""
                    INSERT INTO users (email, password_hash, first_name, last_name, phone, address)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (email.lower(), password_hash, first_name, last_name, phone, address))
                
                user_id = cursor.lastrowid
                conn.commit()
                
                return True, user_id
                
        except Exception as e:
            print(f"User creation error: {e}")
            return False, "Hesap oluşturulurken bir hata oluştu"
    
    @staticmethod
    def authenticate_user(email, password):
        """Authenticate user login"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, password_hash, first_name, last_name, is_active
                    FROM users WHERE email = ?
                """, (email.lower(),))
                
                user = cursor.fetchone()
                if not user:
                    return False, "Email veya şifre hatalı"
                
                if not user['is_active']:
                    return False, "Hesabınız deaktive edilmiştir"
                
                if check_password_hash(user['password_hash'], password):
                    # Update last login
                    cursor.execute("""
                        UPDATE users SET last_login = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    """, (user['id'],))
                    conn.commit()
                    
                    return True, {
                        'id': user['id'],
                        'first_name': user['first_name'],
                        'last_name': user['last_name'],
                        'email': email.lower()
                    }
                else:
                    return False, "Email veya şifre hatalı"
                    
        except Exception as e:
            print(f"Authentication error: {e}")
            return False, "Giriş yapılırken bir hata oluştu"
    
    @staticmethod
    def get_user_by_id(user_id):
        """Get user by ID"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, email, first_name, last_name, phone, address, created_at, last_login
                    FROM users WHERE id = ? AND is_active = 1
                """, (user_id,))
                
                user = cursor.fetchone()
                return dict(user) if user else None
                
        except Exception as e:
            print(f"Get user error: {e}")
            return None

# User authentication decorator
def user_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_logged_in") or not session.get("user_id"):
            return redirect(url_for("user_login"))
        return f(*args, **kwargs)
    return decorated_function

# Initialize user manager
user_manager = UserManager()


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



@app.route("/api/filter_products")
@rate_limit(30, 60)  # Max 30 filter requests per minute
@monitor_performance
def filter_products():
    """AJAX için dinamik ürün filtreleme endpoint'i (optimized with brand support)"""
    selected_category = session.get("selected_category")
    if not selected_category:
        return jsonify({"error": "Kategori seçilmemiş"}), 400

    category = selected_category
    main_category = request.args.get("main_category", "")
    subcategory = request.args.get("subcategory", "")
    brand = request.args.get("brand", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")
    sort_by = request.args.get("sort", "name")  # New sorting parameter

    try:
        # Use cached product data with brand filtering
        products = get_products_by_category(category, brand, min_price, max_price)
        
        # Apply subcategory filtering
        filtered_products = filter_products_by_subcategory(products, main_category, subcategory)
        
        # Apply sorting
        if sort_by == "price-asc":
            filtered_products.sort(key=lambda x: float(x.get('price', 0)))
        elif sort_by == "price-desc":
            filtered_products.sort(key=lambda x: float(x.get('price', 0)), reverse=True)
        elif sort_by == "newest":
            filtered_products.sort(key=lambda x: x.get('id', 0), reverse=True)
        elif sort_by == "name":
            filtered_products.sort(key=lambda x: x.get('name', '').lower())
        
        # Convert to JSON format with enhanced data
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
                "description": p.get("description", ""),
                "in_stock": p.get("in_stock", 1)
            }
            json_products.append(product_dict)
            
        return jsonify({
            "products": json_products, 
            "count": len(json_products),
            "filters": {
                "brand": brand,
                "main_category": main_category,
                "subcategory": subcategory,
                "price_range": [min_price, max_price],
                "sort": sort_by
            }
        })
    except Exception as e:
        print(f"Database error in filter_products: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/contact", methods=["GET", "POST"])
@rate_limit(5, 300)  # Max 5 contact form submissions per 5 minutes
def contact():
    message = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        msg = request.form.get("message", "").strip()
        
        # Enhanced validation
        if not validate_text_input(name, 100, 2):
            message = "Geçerli bir isim girin (2-100 karakter)."
        elif not validate_text_input(email, 254, 5) or '@' not in email:
            message = "Geçerli bir email adresi girin."
        elif not validate_text_input(msg, 1000, 10):
            message = "Mesaj 10-1000 karakter arası olmalıdır."
        else:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO messages (name, email, phone, message) VALUES (?, ?, ?, ?)", 
                             (name[:100], email[:254], phone[:20], msg[:1000]))
                conn.commit()
                conn.close()
                message = "Mesajınız başarıyla gönderildi!"
            except Exception as e:
                print(f"Contact form error: {e}")
                message = "Bir hata oluştu. Lütfen tekrar deneyin."
    
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
        
        # Invalidate relevant caches
        invalidate_product_cache(category)
        invalidate_brand_cache()
        
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
    cursor.execute("SELECT id, name, price, stock_quantity FROM products WHERE id = ? AND in_stock = 1", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return "Ürün bulunamadı veya stokta yok", 404

    current_stock = product[3] or 0
    
    # Check if product is available in stock
    if current_stock <= 0:
        session['cart_message'] = f"{product[1]} şu anda stokta bulunmuyor."
        return redirect(url_for("index"))

    item = {"id": product[0], "name": product[1], "price": product[2], "quantity": 1}

    if "cart" not in session:
        session["cart"] = []

    # Check current quantity in cart
    current_cart_quantity = 0
    for cart_item in session["cart"]:
        if cart_item["id"] == item["id"]:
            current_cart_quantity = cart_item["quantity"]
            break
    
    # Check if adding one more would exceed stock
    if current_cart_quantity + 1 > current_stock:
        session['cart_message'] = f"{product[1]} için yeterli stok bulunmuyor. Stokta: {current_stock}"
        return redirect(url_for("index"))

    # Add to cart or increase quantity
    for cart_item in session["cart"]:
        if cart_item["id"] == item["id"]:
            cart_item["quantity"] += 1
            break
    else:
        session["cart"].append(item)

    session.modified = True
    session['cart_message'] = f"{product[1]} sepete eklendi!"
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
    
    # Get product category before deletion for cache invalidation
    cursor.execute("SELECT category FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    category = product[0] if product else None
    
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    
    # Invalidate relevant caches
    if category:
        invalidate_product_cache(category)
        invalidate_brand_cache()
    
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

        # Veritabanına kaydet ve stokları güncelle
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, check all items are still in stock
        all_available = True
        stock_issues = []
        
        for item in cart_items:
            cursor.execute("SELECT stock_quantity, name FROM products WHERE id = ?", (item['id'],))
            product = cursor.fetchone()
            if product:
                available_stock = product[0] or 0
                required_quantity = item.get('quantity', 1)
                if available_stock < required_quantity:
                    all_available = False
                    stock_issues.append(f"{product[1]}: {required_quantity} istendi, {available_stock} mevcut")
        
        if not all_available:
            conn.close()
            return f"Stok yetersiz: {', '.join(stock_issues)}", 400
        
        # Create order
        cursor.execute("""
            INSERT INTO orders (order_code, items, total_price, customer_name, customer_phone, customer_email, customer_address, address, note, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_code, json.dumps(cart_items), total, customer_name, phone, email, address, address, note, 'Hazırlanıyor'))
        
        # Update stock for each item and check for low stock
        for item in cart_items:
            quantity_sold = item.get('quantity', 1)
            update_product_stock(item['id'], -quantity_sold, f"Satış - Sipariş: {order_code}")
            
            # Check if stock is now low and send notification
            cursor.execute("SELECT name, stock_quantity, low_stock_threshold FROM products WHERE id = ?", (item['id'],))
            product = cursor.fetchone()
            if product:
                current_stock = product[1] or 0
                threshold = product[2] or 5
                if current_stock <= threshold:
                    notification_service.notify_low_stock(product[0], current_stock, threshold)
        
        conn.commit()
        conn.close()
        
        # Send order confirmation email
        order_data = {
            'order_code': order_code,
            'customer_name': customer_name,
            'customer_email': email,
            'customer_phone': phone,
            'total_price': total,
            'items': cart_items
        }
        
        # Send order confirmation notification
        if email:
            subject = f"Sipariş Onayı - {order_code}"
            body = f"""
Merhaba {customer_name},

Siparişiniz başarıyla alındı!

Sipariş Kodu: {order_code}
Toplam Tutar: {total} TL

Ürünler:
"""
            for item in cart_items:
                body += f"- {item['name']} x{item.get('quantity', 1)} = {item['price'] * item.get('quantity', 1)} TL\n"
            
            body += f"""
Adres: {address}

Siparişinizi takip etmek için: https://mavipetshop.com/order-track

Teşekkürler,
Mavi Petshop Ekibi
            """
            
            notification_service.send_email(email, subject, body)

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
        
        # Invalidate relevant caches
        invalidate_product_cache(category)
        invalidate_brand_cache()
        
        return redirect(url_for("admin_panel"))

    return render_template("add_product.html")


# Removed duplicate product_detail route - using enhanced version below


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
        
        # Get order data for notification before update
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order_row = cursor.fetchone()
        order_data = dict(order_row) if order_row else None
        
        # Durumu güncelle
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        
        # Send notification to customer
        if order_data:
            notification_service.notify_order_status_change(order_data, new_status)
        
        return jsonify({"success": True, "message": "Sipariş durumu güncellendi ve müşteri bilgilendirildi"})
    
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

# USER AUTHENTICATION ROUTES

@app.route("/register", methods=["GET", "POST"])
@rate_limit(10, 300)  # Max 10 registrations per 5 minutes
def user_register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        
        # Validation
        if password != confirm_password:
            return render_template("user_register.html", error="Şifreler eşleşmiyor")
        
        success, result = user_manager.create_user(
            email, password, first_name, last_name, phone or None, address or None
        )
        
        if success:
            # Auto-login after registration
            session["user_logged_in"] = True
            session["user_id"] = result
            session["user_name"] = f"{first_name} {last_name}"
            session["user_email"] = email.lower()
            
            # Send welcome email
            if notification_service.email_enabled:
                welcome_subject = "🐾 Mavi Petshop'a Hoş Geldiniz!"
                welcome_body = f"""
Merhaba {first_name},

Mavi Petshop ailesine hoş geldiniz! 🎉

Hesabınız başarıyla oluşturuldu. Artık:
✅ Sipariş verebilir ve takip edebilirsiniz
✅ Favori ürünlerinizi kaydedebilirsiniz  
✅ Ürünlere yorum yazabilirsiniz
✅ Özel kampanyalarımızdan haberdar olabilirsiniz

Keyifli alışverişler dileriz!

Mavi Petshop Ekibi
                """
                notification_service.send_email(email, welcome_subject, welcome_body)
            
            return redirect(url_for("index"))
        else:
            return render_template("user_register.html", error=result)
    
    return render_template("user_register.html")

@app.route("/login", methods=["GET", "POST"])
@rate_limit(20, 300)  # Max 20 login attempts per 5 minutes
def user_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember_me = request.form.get("remember_me")
        
        success, result = user_manager.authenticate_user(email, password)
        
        if success:
            session["user_logged_in"] = True
            session["user_id"] = result["id"]
            session["user_name"] = f"{result['first_name']} {result['last_name']}"
            session["user_email"] = result["email"]
            
            # Set permanent session if remember me is checked
            if remember_me:
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=30)
            
            # Redirect to intended page or index
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for("index"))
        else:
            return render_template("user_login.html", error=result)
    
    return render_template("user_login.html")

@app.route("/logout")
def user_logout():
    # Clear user session
    user_keys = ["user_logged_in", "user_id", "user_name", "user_email"]
    for key in user_keys:
        session.pop(key, None)
    
    session.permanent = False
    return redirect(url_for("index"))

@app.route("/profile")
@user_login_required
def user_profile():
    user = user_manager.get_user_by_id(session["user_id"])
    if not user:
        return redirect(url_for("user_logout"))
    
    # Get user's recent orders
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders 
                WHERE customer_email = ? 
                ORDER BY created_at DESC 
                LIMIT 10
            """, (user["email"],))
            
            orders = []
            for order_row in cursor.fetchall():
                order = dict(order_row)
                try:
                    order["items"] = json.loads(order["items"])
                    if order["created_at"]:
                        order["created_at"] = datetime.strptime(order["created_at"], "%Y-%m-%d %H:%M:%S")
                except:
                    order["items"] = []
                    order["created_at"] = datetime.now()
                orders.append(order)
                
        # Get wishlist count
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM wishlist WHERE user_id = ?", (user["id"],))
            wishlist_count = cursor.fetchone()["count"]
            
    except Exception as e:
        print(f"Profile data error: {e}")
        orders = []
        wishlist_count = 0
    
    return render_template("user_profile.html", 
                         user=user, 
                         orders=orders, 
                         wishlist_count=wishlist_count)

@app.route("/profile/edit", methods=["GET", "POST"])
@user_login_required
def edit_profile():
    user = user_manager.get_user_by_id(session["user_id"])
    if not user:
        return redirect(url_for("user_logout"))
    
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        
        if not first_name or not last_name:
            return render_template("edit_profile.html", user=user, error="Ad ve soyad zorunludur")
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET first_name = ?, last_name = ?, phone = ?, address = ?
                    WHERE id = ?
                """, (first_name, last_name, phone or None, address or None, user["id"]))
                conn.commit()
                
                # Update session data
                session["user_name"] = f"{first_name} {last_name}"
                
                return redirect(url_for("user_profile"))
                
        except Exception as e:
            print(f"Profile update error: {e}")
            return render_template("edit_profile.html", user=user, error="Profil güncellenirken bir hata oluştu")
    
    return render_template("edit_profile.html", user=user)

# WISHLIST SYSTEM ROUTES

@app.route("/wishlist")
@user_login_required
def user_wishlist():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, w.created_at as added_date
                FROM wishlist w
                JOIN products p ON w.product_id = p.id
                WHERE w.user_id = ? AND p.in_stock = 1
                ORDER BY w.created_at DESC
            """, (session["user_id"],))
            
            wishlist_items = []
            for row in cursor.fetchall():
                item = dict(row)
                try:
                    if item.get('subcategory'):
                        item['subcategory'] = json.loads(item['subcategory'])
                except:
                    item['subcategory'] = []
                
                if item['added_date']:
                    try:
                        item['added_date'] = datetime.strptime(item['added_date'], "%Y-%m-%d %H:%M:%S")
                    except:
                        item['added_date'] = datetime.now()
                        
                wishlist_items.append(item)
                
    except Exception as e:
        print(f"Wishlist error: {e}")
        wishlist_items = []
    
    return render_template("user_wishlist.html", wishlist_items=wishlist_items)

@app.route("/api/wishlist/add/<int:product_id>", methods=["POST"])
@user_login_required
@rate_limit(30, 60)  # Max 30 wishlist operations per minute
def add_to_wishlist(product_id):
    try:
        user_id = session["user_id"]
        
        # Check if product exists and is in stock
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM products WHERE id = ? AND in_stock = 1", (product_id,))
            product = cursor.fetchone()
            
            if not product:
                return jsonify({"success": False, "message": "Ürün bulunamadı"}), 404
            
            # Check if already in wishlist
            cursor.execute("SELECT id FROM wishlist WHERE user_id = ? AND product_id = ?", (user_id, product_id))
            if cursor.fetchone():
                return jsonify({"success": False, "message": "Ürün zaten favorilerinizde"})
            
            # Add to wishlist
            cursor.execute("""
                INSERT INTO wishlist (user_id, product_id)
                VALUES (?, ?)
            """, (user_id, product_id))
            conn.commit()
            
            # Get updated wishlist count
            cursor.execute("SELECT COUNT(*) as count FROM wishlist WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()["count"]
            
            return jsonify({
                "success": True, 
                "message": f"{product['name']} favorilerinize eklendi!",
                "wishlist_count": count
            })
            
    except Exception as e:
        print(f"Add to wishlist error: {e}")
        return jsonify({"success": False, "message": "Bir hata oluştu"}), 500

@app.route("/api/wishlist/remove/<int:product_id>", methods=["POST"])
@user_login_required
@rate_limit(30, 60)
def remove_from_wishlist(product_id):
    try:
        user_id = session["user_id"]
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get product name before deletion
            cursor.execute("""
                SELECT p.name FROM wishlist w
                JOIN products p ON w.product_id = p.id
                WHERE w.user_id = ? AND w.product_id = ?
            """, (user_id, product_id))
            
            result = cursor.fetchone()
            if not result:
                return jsonify({"success": False, "message": "Ürün favorilerinizde değil"})
            
            product_name = result["name"]
            
            # Remove from wishlist
            cursor.execute("DELETE FROM wishlist WHERE user_id = ? AND product_id = ?", (user_id, product_id))
            conn.commit()
            
            # Get updated wishlist count
            cursor.execute("SELECT COUNT(*) as count FROM wishlist WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()["count"]
            
            return jsonify({
                "success": True, 
                "message": f"{product_name} favorilerinizden çıkarıldı",
                "wishlist_count": count
            })
            
    except Exception as e:
        print(f"Remove from wishlist error: {e}")
        return jsonify({"success": False, "message": "Bir hata oluştu"}), 500

@app.route("/api/wishlist/check/<int:product_id>")
@user_login_required
def check_wishlist_status(product_id):
    try:
        user_id = session["user_id"]
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM wishlist WHERE user_id = ? AND product_id = ?", (user_id, product_id))
            in_wishlist = cursor.fetchone() is not None
            
            return jsonify({"in_wishlist": in_wishlist})
            
    except Exception as e:
        print(f"Check wishlist error: {e}")
        return jsonify({"in_wishlist": False})

# REVIEW & RATING SYSTEM

@app.route("/api/reviews/<int:product_id>")
def get_product_reviews(product_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, u.first_name, u.last_name
                FROM reviews r
                JOIN users u ON r.user_id = u.id
                WHERE r.product_id = ?
                ORDER BY r.created_at DESC
            """, (product_id,))
            
            reviews = []
            total_rating = 0
            rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            
            for row in cursor.fetchall():
                review = dict(row)
                review['author_name'] = f"{review['first_name']} {review['last_name'][0]}."
                
                # Format date
                if review['created_at']:
                    try:
                        review['created_at'] = datetime.strptime(review['created_at'], "%Y-%m-%d %H:%M:%S")
                    except:
                        review['created_at'] = datetime.now()
                
                reviews.append(review)
                total_rating += review['rating']
                rating_counts[review['rating']] += 1
            
            # Calculate average rating
            avg_rating = round(total_rating / len(reviews), 1) if reviews else 0
            
            return jsonify({
                "reviews": reviews,
                "stats": {
                    "total_reviews": len(reviews),
                    "average_rating": avg_rating,
                    "rating_distribution": rating_counts
                }
            })
            
    except Exception as e:
        print(f"Get reviews error: {e}")
        return jsonify({"reviews": [], "stats": {"total_reviews": 0, "average_rating": 0, "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}}})

@app.route("/api/reviews/submit", methods=["POST"])
@user_login_required
@rate_limit(5, 300)  # Max 5 reviews per 5 minutes
def submit_review():
    try:
        data = request.get_json()
        user_id = session["user_id"]
        product_id = data.get("product_id")
        rating = data.get("rating")
        title = data.get("title", "").strip()
        comment = data.get("comment", "").strip()
        
        # Validation
        if not product_id or not rating:
            return jsonify({"success": False, "message": "Ürün ve puan bilgisi gereklidir"})
        
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({"success": False, "message": "Puan 1-5 arasında olmalıdır"})
        
        if len(comment) > 1000:
            return jsonify({"success": False, "message": "Yorum çok uzun (max 1000 karakter)"})
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if product exists
            cursor.execute("SELECT id, name FROM products WHERE id = ?", (product_id,))
            product = cursor.fetchone()
            if not product:
                return jsonify({"success": False, "message": "Ürün bulunamadı"})
            
            # Check if user already reviewed this product
            cursor.execute("SELECT id FROM reviews WHERE user_id = ? AND product_id = ?", (user_id, product_id))
            if cursor.fetchone():
                return jsonify({"success": False, "message": "Bu ürün için zaten yorum yazmışsınız"})
            
            # Insert review
            cursor.execute("""
                INSERT INTO reviews (user_id, product_id, rating, title, comment)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, product_id, rating, title or None, comment or None))
            
            conn.commit()
            
            return jsonify({
                "success": True, 
                "message": "Yorumunuz başarıyla kaydedildi!"
            })
            
    except Exception as e:
        print(f"Submit review error: {e}")
        return jsonify({"success": False, "message": "Bir hata oluştu"})

@app.route("/reviews/manage")
@user_login_required
def manage_user_reviews():
    try:
        user_id = session["user_id"]
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, p.name as product_name, p.image as product_image
                FROM reviews r
                JOIN products p ON r.product_id = p.id
                WHERE r.user_id = ?
                ORDER BY r.created_at DESC
            """, (user_id,))
            
            user_reviews = []
            for row in cursor.fetchall():
                review = dict(row)
                if review['created_at']:
                    try:
                        review['created_at'] = datetime.strptime(review['created_at'], "%Y-%m-%d %H:%M:%S")
                    except:
                        review['created_at'] = datetime.now()
                user_reviews.append(review)
                
    except Exception as e:
        print(f"Manage reviews error: {e}")
        user_reviews = []
    
    return render_template("user_reviews.html", user_reviews=user_reviews)

# Add to product detail route to include reviews
@app.route("/product/<int:product_id>")
def product_detail(product_id):
    try:
        print(f"🔍 Product detail requested for ID: {product_id}")
        print(f"🗄️ Database path: {db_path}")
        print(f"📁 Database exists: {os.path.exists(db_path)}")
        
        # Direct database connection as fallback
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            print(f"📊 Direct database connection established")
            
            # Check if products table exists and has data
            cursor.execute("SELECT COUNT(*) FROM products")
            product_count = cursor.fetchone()[0]
            print(f"📦 Total products in database: {product_count}")
            
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = cursor.fetchone()
            print(f"🎯 Product query result: {product is not None}")
            
            if product:
                print(f"✅ Product found: {dict(product)}")
            
            if not product:
                print(f"❌ Product {product_id} not found in database")
                
                # Emergency: If database is empty, add sample products NOW!
                if product_count == 0:
                    print("🚨 EMERGENCY: Database empty, adding sample products NOW!")
                    sample_products = [
                        ("Royal Canin Kitten Mama", 450.0, "/static/uploads/1.webp", "Kedi", '["Mama"]', "2-12 aylık yavrular için özel formül kedi maması", "Royal Canin"),
                        ("Lavital Kitten Somonlu Yavru Kedi Maması 1.5 KG", 340.0, "/static/uploads/2.webp", "Kedi", '["Mama"]', "6-52 hafta - 12 aylık dönemdeki yavru kediler için özel formüle edilen bir yavru kedi mamasıdır.", "Lavital"),
                        ("Whiskas Yetişkin Kedi Maması", 280.0, "/static/uploads/3.webp", "Kedi", '["Mama"]', "Yetişkin kediler için dengeli beslenme", "Whiskas"),
                        ("Pro Plan Köpek Maması", 520.0, "/static/uploads/4.webp", "Köpek", '["Mama"]', "Yetişkin köpekler için premium mama", "Pro Plan"),
                        ("Pedigree Köpek Maması", 380.0, "/static/uploads/5.webp", "Köpek", '["Mama"]', "Köpeklerin sağlıklı yaşamı için", "Pedigree"),
                        ("Kedi Oyuncağı Top", 45.0, "/static/uploads/6.webp", "Kedi", '["Oyuncak"]', "Renkli kedi oyun topu", "Generic"),
                        ("Köpek Tasması", 120.0, "/static/uploads/7.webp", "Köpek", '["Aksesuar"]', "Ayarlanabilir köpek tasması", "Generic"),
                        ("Kedi Kumu 10L", 85.0, "/static/uploads/8.webp", "Kedi", '["Bakım"]', "Kokusuz kedi kumu", "Generic"),
                        ("Balık Yemi", 25.0, "/static/uploads/9.webp", "Balık", '["Yem"]', "Tropikal balıklar için yem", "Generic"),
                        ("Kuş Yemi", 35.0, "/static/uploads/10.webp", "Kuş", '["Yem"]', "Muhabbet kuşları için karma yem", "Generic"),
                    ]
                    
                    for product_data in sample_products:
                        cursor.execute("""
                            INSERT INTO products (name, price, image, category, subcategory, description, brand, in_stock)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                        """, product_data)
                    
                    conn.commit()
                    print(f"🆘 EMERGENCY: {len(sample_products)} products added!")
                    
                    # Try again after adding products
                    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
                    product = cursor.fetchone()
                    
                    if product:
                        print(f"✅ RECOVERED: Product {product_id} now found after emergency insert!")
                        # Continue normal flow
                    else:
                        print(f"💀 STILL NOT FOUND: Product {product_id} even after emergency insert")
                
                if not product:
                    # Show available products
                    cursor.execute("SELECT id, name FROM products LIMIT 10")
                    available = cursor.fetchall()
                    print(f"📋 Available products: {[dict(p) for p in available]}")
                    return render_template("404.html"), 404
            
            product = dict(product)
            
            # Parse subcategory JSON
            if product.get('subcategory'):
                try:
                    product['subcategory'] = json.loads(product['subcategory'])
                except:
                    product['subcategory'] = []
            
            # Get reviews (only if tables exist)
            reviews = []
            avg_rating = 0
            user_reviewed = False
            
            try:
                # Check if reviews and users tables exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
                reviews_table_exists = cursor.fetchone()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                users_table_exists = cursor.fetchone()
                
                if reviews_table_exists and users_table_exists:
                    cursor.execute("""
                        SELECT r.*, u.first_name, u.last_name
                        FROM reviews r
                        JOIN users u ON r.user_id = u.id
                        WHERE r.product_id = ?
                        ORDER BY r.created_at DESC
                        LIMIT 5
                    """, (product_id,))
                    
                    total_rating = 0
                    
                    for row in cursor.fetchall():
                        review = dict(row)
                        review['author_name'] = f"{review['first_name']} {review['last_name'][0]}."
                        
                        if review['created_at']:
                            try:
                                review['created_at'] = datetime.strptime(review['created_at'], "%Y-%m-%d %H:%M:%S")
                            except:
                                review['created_at'] = datetime.now()
                        
                        reviews.append(review)
                        total_rating += review['rating']
                    
                    # Calculate average rating
                    avg_rating = round(total_rating / len(reviews), 1) if reviews else 0
                    
                    # Check if user already reviewed (if logged in)
                    if session.get("user_logged_in"):
                        cursor.execute("SELECT id FROM reviews WHERE user_id = ? AND product_id = ?", 
                                     (session["user_id"], product_id))
                        user_reviewed = cursor.fetchone() is not None
            except Exception as reviews_error:
                print(f"Reviews check error (normal if tables don't exist): {reviews_error}")
                reviews = []
                avg_rating = 0
                user_reviewed = False
            
            return render_template("product_detail.html", 
                                 product=product, 
                                 reviews=reviews,
                                 avg_rating=avg_rating,
                                 total_reviews=len(reviews),
                                 user_reviewed=user_reviewed)
        finally:
            if conn:
                conn.close()
            
    except Exception as e:
        print(f"💥 Product detail error: {e}")
        print(f"🔍 Error type: {type(e).__name__}")
        import traceback
        print(f"📋 Full traceback: {traceback.format_exc()}")
        return render_template("404.html"), 404

# ERROR HANDLERS

@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning(f'404 error: {request.url}')
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'500 error: {error}')
    app.logger.error(traceback.format_exc())
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    app.logger.warning(f'403 error: {request.url}')
    return render_template('403.html'), 403

@app.errorhandler(429)
def rate_limit_error(error):
    app.logger.warning(f'429 rate limit exceeded: {request.url} from {get_client_ip()}')
    return render_template('429.html'), 429

# Health check endpoint for monitoring
@app.route("/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

# Sitemap for SEO
@app.route("/sitemap.xml")
def sitemap():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get all products
            cursor.execute("SELECT id FROM products WHERE in_stock = 1")
            products = cursor.fetchall()
            
            # Get all categories
            cursor.execute("SELECT DISTINCT category FROM products WHERE in_stock = 1")
            categories = cursor.fetchall()
            
        sitemap_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://mavipetshop.com/</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://mavipetshop.com/contact</loc>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>
    </url>
    <url>
        <loc>https://mavipetshop.com/order-track</loc>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>'''

        # Add product URLs
        for product in products:
            sitemap_xml += f'''
    <url>
        <loc>https://mavipetshop.com/product/{product['id']}</loc>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>'''

        # Add category URLs (if you have category pages)
        for category in categories:
            sitemap_xml += f'''
    <url>
        <loc>https://mavipetshop.com/category/{category['category']}</loc>
        <changefreq>weekly</changefreq>
        <priority>0.7</priority>
    </url>'''

        sitemap_xml += '''
</urlset>'''

        response = app.response_class(
            response=sitemap_xml,
            status=200,
            mimetype='application/xml'
        )
        return response
        
    except Exception as e:
        app.logger.error(f"Sitemap generation error: {e}")
        return "Error generating sitemap", 500

# Robots.txt for SEO
@app.route("/robots.txt")
def robots():
    robots_txt = '''User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Disallow: /cart
Disallow: /profile
Disallow: /login
Disallow: /register

Sitemap: https://mavipetshop.com/sitemap.xml'''
    
    response = app.response_class(
        response=robots_txt,
        status=200,
        mimetype='text/plain'
    )
    return response

# NEWSLETTER SYSTEM

@app.route("/api/newsletter/subscribe", methods=["POST"])
@rate_limit(10, 300)  # Max 10 newsletter subscriptions per 5 minutes
def newsletter_subscribe():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        
        # Validate email
        if not user_manager.validate_email(email):
            return jsonify({"success": False, "message": "Geçersiz email formatı"})
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if already subscribed
            cursor.execute("SELECT id, is_active FROM newsletter_subscriptions WHERE email = ?", (email,))
            existing = cursor.fetchone()
            
            if existing:
                if existing['is_active']:
                    return jsonify({"success": False, "message": "Bu email adresi zaten newsletter'a kayıtlı"})
                else:
                    # Reactivate subscription
                    cursor.execute("""
                        UPDATE newsletter_subscriptions 
                        SET is_active = 1, unsubscribed_at = NULL
                        WHERE email = ?
                    """, (email,))
                    conn.commit()
                    
                    return jsonify({"success": True, "message": "Newsletter aboneliğiniz yeniden aktif edildi!"})
            else:
                # New subscription
                cursor.execute("""
                    INSERT INTO newsletter_subscriptions (email)
                    VALUES (?)
                """, (email,))
                conn.commit()
                
                # Send welcome email
                if notification_service.email_enabled:
                    welcome_subject = "🐾 Mavi Petshop Newsletter'a Hoş Geldiniz!"
                    welcome_body = f"""
Merhaba,

Mavi Petshop newsletter'ına abone olduğunuz için teşekkürler! 🎉

Artık:
✅ Özel kampanyalarımızdan ilk siz haberdar olacaksınız
✅ Yeni ürün duyurularını alacaksınız
✅ İndirim kuponlarına erişebileceksiniz
✅ Evcil hayvan bakım ipuçlarını öğreneceksiniz

Newsletter'dan çıkmak için: https://mavipetshop.com/newsletter/unsubscribe?email={email}

Mavi Petshop Ekibi
                    """
                    notification_service.send_email(email, welcome_subject, welcome_body)
                
                return jsonify({"success": True, "message": "Newsletter'a başarıyla abone oldunuz!"})
                
    except Exception as e:
        app.logger.error(f"Newsletter subscription error: {e}")
        return jsonify({"success": False, "message": "Bir hata oluştu"}), 500

@app.route("/newsletter/unsubscribe")
def newsletter_unsubscribe():
    email = request.args.get("email", "").strip().lower()
    
    if not email:
        return render_template("newsletter_unsubscribe.html", error="Email adresi gereklidir")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM newsletter_subscriptions WHERE email = ? AND is_active = 1", (email,))
            
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE newsletter_subscriptions 
                    SET is_active = 0, unsubscribed_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                """, (email,))
                conn.commit()
                
                return render_template("newsletter_unsubscribe.html", success=True, email=email)
            else:
                return render_template("newsletter_unsubscribe.html", error="Bu email adresi newsletter'da kayıtlı değil")
                
    except Exception as e:
        app.logger.error(f"Newsletter unsubscribe error: {e}")
        return render_template("newsletter_unsubscribe.html", error="Bir hata oluştu")

@app.route("/admin/newsletter")
@login_required
def admin_newsletter():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get newsletter statistics
            cursor.execute("SELECT COUNT(*) as total FROM newsletter_subscriptions WHERE is_active = 1")
            active_subscribers = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as total FROM newsletter_subscriptions WHERE is_active = 0")
            unsubscribed = cursor.fetchone()['total']
            
            # Get recent subscribers
            cursor.execute("""
                SELECT email, created_at FROM newsletter_subscriptions 
                WHERE is_active = 1
                ORDER BY created_at DESC
                LIMIT 50
            """)
            recent_subscribers = [dict(row) for row in cursor.fetchall()]
            
            stats = {
                'active_subscribers': active_subscribers,
                'unsubscribed': unsubscribed,
                'total': active_subscribers + unsubscribed
            }
            
    except Exception as e:
        app.logger.error(f"Admin newsletter error: {e}")
        stats = {'active_subscribers': 0, 'unsubscribed': 0, 'total': 0}
        recent_subscribers = []
    
    return render_template("admin_newsletter.html", stats=stats, subscribers=recent_subscribers)

@app.route("/admin/newsletter/send", methods=["POST"])
@login_required
@rate_limit(5, 3600)  # Max 5 newsletter sends per hour
def admin_send_newsletter():
    try:
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        
        if not subject or not message:
            return jsonify({"success": False, "message": "Konu ve mesaj alanları zorunludur"})
        
        if not notification_service.email_enabled:
            return jsonify({"success": False, "message": "Email servisi aktif değil"})
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM newsletter_subscriptions WHERE is_active = 1")
            subscribers = [row['email'] for row in cursor.fetchall()]
        
        if not subscribers:
            return jsonify({"success": False, "message": "Aktif abone bulunamadı"})
        
        # Send emails (in background to avoid timeout)
        import threading
        
        def send_bulk_emails():
            success_count = 0
            for email in subscribers:
                try:
                    # Add unsubscribe link to message
                    full_message = f"""
{message}

---
Bu newsletter'dan çıkmak için: https://mavipetshop.com/newsletter/unsubscribe?email={email}

Mavi Petshop Ekibi
                    """
                    
                    if notification_service.send_email(email, f"🐾 {subject}", full_message):
                        success_count += 1
                        
                except Exception as e:
                    app.logger.error(f"Newsletter send error for {email}: {e}")
            
            app.logger.info(f"Newsletter sent to {success_count}/{len(subscribers)} subscribers")
        
        # Start background thread
        thread = threading.Thread(target=send_bulk_emails)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True, 
            "message": f"Newsletter {len(subscribers)} aboneye gönderiliyor..."
        })
        
    except Exception as e:
        app.logger.error(f"Admin send newsletter error: {e}")
        return jsonify({"success": False, "message": "Bir hata oluştu"}), 500


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
    
    # Stock statistics
    try:
        stock_stats = get_stock_statistics()
        low_stock_products = get_low_stock_products()
    except:
        stock_stats = {'low_stock_count': 0, 'total_stock_value': 0}
        low_stock_products = []
    
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
                         recent_orders=recent_orders,
                         stock_stats=stock_stats,
                         low_stock_products=low_stock_products)


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
            
            # Invalidate campaign cache
            invalidate_campaign_cache()
            
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

@app.route("/admin/stock", methods=["GET", "POST"])
@login_required
def admin_stock():
    message = None
    
    # Handle stock updates
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_stock":
            product_id = request.form.get("product_id")
            new_quantity = request.form.get("quantity")
            threshold = request.form.get("threshold")
            
            try:
                product_id = int(product_id)
                new_quantity = int(new_quantity) if new_quantity else 0
                threshold = int(threshold) if threshold else 5
                
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get current stock
                    cursor.execute("SELECT stock_quantity, name FROM products WHERE id = ?", (product_id,))
                    product = cursor.fetchone()
                    
                    if product:
                        old_quantity = product['stock_quantity'] or 0
                        
                        cursor.execute("""
                            UPDATE products 
                            SET stock_quantity = ?, 
                                low_stock_threshold = ?,
                                last_restocked = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (new_quantity, threshold, product_id))
                        
                        conn.commit()
                        
                        # Invalidate caches
                        invalidate_product_cache()
                        cache.delete_memoized(get_low_stock_products)
                        cache.delete_memoized(get_stock_statistics)
                        
                        message = f"✅ {product['name']} stoku güncellendi: {old_quantity} → {new_quantity}"
                    else:
                        message = "❌ Ürün bulunamadı"
                        
            except ValueError:
                message = "❌ Geçersiz sayı formatı"
            except Exception as e:
                message = f"❌ Hata: {str(e)}"
    
    # Get stock data
    try:
        stock_stats = get_stock_statistics()
        low_stock_products = get_low_stock_products()
        
        # Get all products with stock info
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, category, brand, price, stock_quantity, 
                       low_stock_threshold, last_restocked, in_stock
                FROM products 
                ORDER BY 
                    CASE WHEN stock_quantity <= COALESCE(low_stock_threshold, 5) THEN 0 ELSE 1 END,
                    stock_quantity ASC, name ASC
            """)
            all_products = []
            for row in cursor.fetchall():
                product = dict(row)
                # Format last_restocked
                if product['last_restocked']:
                    try:
                        product['last_restocked'] = datetime.strptime(product['last_restocked'], "%Y-%m-%d %H:%M:%S")
                    except:
                        product['last_restocked'] = None
                all_products.append(product)
                
    except Exception as e:
        print(f"Stock data error: {e}")
        stock_stats = {'low_stock_count': 0, 'total_stock_value': 0, 'total_stock_units': 0}
        low_stock_products = []
        all_products = []
    
    return render_template("admin_stock.html", 
                         stock_stats=stock_stats,
                         low_stock_products=low_stock_products,
                         all_products=all_products,
                         message=message)


@app.route("/admin/update_order_status/<int:order_id>", methods=["POST"], endpoint="update_order_status_form")
@login_required  
def update_order_status_form(order_id):
    new_status = request.form.get("status", "Hazırlanıyor")
    shipping_company = request.form.get("shipping_company", "")
    tracking_number = request.form.get("tracking_number", "")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get order data for notification before update
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order_row = cursor.fetchone()
    order_data = dict(order_row) if order_row else None
    
    cursor.execute("UPDATE orders SET status = ?, shipping_company = ?, tracking_number = ? WHERE id = ?", (new_status, shipping_company, tracking_number, order_id))
    conn.commit()
    conn.close()
    
    # Send notification to customer
    if order_data:
        notification_service.notify_order_status_change(order_data, new_status)
    
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


@app.route("/api/brands")
@cache.memoize(timeout=3600)
@monitor_performance
def get_brands():
    """Get all available brands for filtering"""
    try:
        category = session.get("selected_category")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get distinct brands for the selected category
            if category:
                cursor.execute("""
                    SELECT DISTINCT brand FROM products 
                    WHERE brand IS NOT NULL AND brand != '' 
                    AND in_stock = 1 AND LOWER(category) = LOWER(?)
                    ORDER BY brand
                """, (category,))
            else:
                cursor.execute("""
                    SELECT DISTINCT brand FROM products 
                    WHERE brand IS NOT NULL AND brand != '' 
                    AND in_stock = 1
                    ORDER BY brand
                """)
            
            brands = [row[0] for row in cursor.fetchall()]
            return jsonify({"brands": brands})
            
    except Exception as e:
        print(f"Brands API error: {e}")
        return jsonify({"brands": []})

@app.route("/api/search")
@rate_limit(30, 60)  # Max 30 search requests per minute
@monitor_performance
def search_products():
    """Real-time product search API with autocomplete"""
    query = request.args.get('q', '').strip()
    category = session.get("selected_category")
    autocomplete = request.args.get('autocomplete', 'false').lower() == 'true'
    
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
            
            # For autocomplete, return suggestions only
            if autocomplete:
                suggestions = set()
                for p in products[:10]:
                    if p['name'] and query.lower() in p['name'].lower():
                        suggestions.add(p['name'])
                    if p['brand'] and query.lower() in p['brand'].lower():
                        suggestions.add(p['brand'])
                
                return jsonify({
                    "suggestions": list(suggestions)[:8],
                    "count": len(products)
                })
            
            # For full search, return products
            return jsonify({
                "products": products[:20],
                "count": len(products)
            })
            
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/suggestions")
@monitor_performance 
def get_suggestions():
    """Get search suggestions for autocomplete - redirects to search API"""
    return search_products()


# Removed duplicate error handlers - using enhanced versions above


@app.template_filter('fromjson')
def fromjson_filter(s):
    return json.loads(s)


def escapejs_filter(value):
    return Markup(json.dumps(str(value)))

app.jinja_env.filters['escapejs'] = escapejs_filter

if __name__ == "__main__":
    app.run(debug=True)