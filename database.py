import sqlite3
from datetime import datetime

DATABASE_NAME = "store.db"

def setup_database():
    """جداول مورد نیاز را در پایگاه داده ایجاد می‌کند."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, price INTEGER NOT NULL, description TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, wallet_balance INTEGER DEFAULT 0)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL, product_name TEXT, price INTEGER, status TEXT NOT NULL, timestamp TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users (user_id), FOREIGN KEY (product_id) REFERENCES products (id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS user_links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, transaction_id INTEGER NOT NULL, product_name TEXT, link TEXT NOT NULL, purchase_date TEXT NOT NULL, is_active BOOLEAN DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users (user_id), FOREIGN KEY (transaction_id) REFERENCES transactions (id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS link_bank (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, link TEXT NOT NULL UNIQUE, is_used BOOLEAN DEFAULT 0, assigned_to_user_id INTEGER, assigned_transaction_id INTEGER, added_date TEXT NOT NULL, FOREIGN KEY (product_id) REFERENCES products (id))""")
    conn.commit()
    conn.close()

def add_links_to_bank(product_id, links):
    """لیستی از لینک‌ها را برای یک محصول خاص به بانک اضافه می‌کند."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    added_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    added_count = 0
    for link in links:
        try:
            cursor.execute("INSERT INTO link_bank (product_id, link, added_date) VALUES (?, ?, ?)", (product_id, link, added_date))
            added_count += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return added_count

def fetch_and_assign_link(product_id, user_id, transaction_id):
    """یک لینک استفاده نشده پیدا کرده، آن را به کاربر اختصاص داده و برمی‌گرداند."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, link FROM link_bank WHERE product_id = ? AND is_used = 0 LIMIT 1", (product_id,))
    result = cursor.fetchone()
    if result:
        link_id, link = result
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE link_bank SET is_used = 1, assigned_to_user_id = ?, assigned_transaction_id = ?, assigned_date = ? WHERE id = ?", (user_id, transaction_id, timestamp, link_id))
        conn.commit()
    conn.close()
    return result[1] if result else None

def get_link_bank_status():
    """تعداد لینک‌های باقی‌مانده برای هر محصول را برمی‌گرداند."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, COUNT(lb.id) FROM products p
        LEFT JOIN link_bank lb ON p.id = lb.product_id AND lb.is_used = 0
        GROUP BY p.name ORDER BY p.id
    """)
    status = cursor.fetchall()
    conn.close()
    return status

def get_product_id_by_name(product_name):
    """ID یک محصول را با استفاده از نام آن پیدا می‌کند."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM products WHERE name = ?", (product_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# (کدهای کامل سایر توابع دیتابیس مانند add_or_update_user, get_products و... را اینجا قرار دهید)
def add_or_update_user(user_id, first_name, username):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET first_name=excluded.first_name, username=excluded.username", (user_id, first_name, username))
    conn.commit()
    conn.close()

def get_products():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products")
    products = cursor.fetchall()
    conn.close()
    return products

def get_product_details(product_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, description FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def create_pending_transaction(user_id, product_id, product_name, price):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO transactions (user_id, product_id, product_name, price, status, timestamp) VALUES (?, ?, ?, ?, 'pending', ?)", (user_id, product_id, product_name, price, timestamp))
    transaction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return transaction_id

def get_transaction(transaction_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, product_name, price, product_id FROM transactions WHERE id = ?", (transaction_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def update_transaction_status(transaction_id, status):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE transactions SET status = ? WHERE id = ?", (status, transaction_id))
    conn.commit()
    conn.close()

def save_user_link(user_id, transaction_id, product_name, link):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    purchase_date = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO user_links (user_id, transaction_id, product_name, link, purchase_date) VALUES (?, ?, ?, ?, ?)",(user_id, transaction_id, product_name, link, purchase_date))
    conn.commit()
    conn.close()

def get_user_links(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT product_name, link, purchase_date FROM user_links WHERE user_id = ? AND is_active = 1",(user_id,))
    links = cursor.fetchall()
    conn.close()
    return links