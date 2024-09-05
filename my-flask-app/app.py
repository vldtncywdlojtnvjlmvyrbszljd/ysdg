import sqlite3
from flask import Flask, request, jsonify, g
from datetime import datetime, timedelta
from flask_cors import CORS
import uuid
import threading
import schedule
import os
import time
import random

# Inisialisasi Flask
app = Flask(__name__)
CORS(app)

# Mengaktifkan mode debug
app.config['DEBUG'] = True

# Fungsi untuk mendapatkan koneksi database per-request
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('keys.db', check_same_thread=False)  # check_same_thread=False agar aman untuk threading
        g.db.row_factory = sqlite3.Row
    return g.db

# Fungsi untuk menutup koneksi database per-request
@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Membuat tabel untuk menyimpan key jika belum ada
with app.app_context():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        created_at INTEGER NOT NULL  -- Menggunakan INTEGER untuk timestamp epoch
    )
    ''')
    db.commit()

# Fungsi untuk men-generate key baru dengan prefiks 'B_Team' dan angka acak
def generate_key():
    random_number = random.randint(100000, 999999)  # Angka acak 6 digit
    return f"B-Team_{random_number}"

# Fungsi untuk menambahkan key baru ke database
def add_key(key):
    db = get_db()
    created_at = int(datetime.utcnow().timestamp())  # Simpan sebagai epoch (integer timestamp)
    cursor = db.cursor()
    try:
        cursor.execute('INSERT INTO keys (key, created_at) VALUES (?, ?)', (key, created_at))
        db.commit()
    except sqlite3.IntegrityError:
        print(f"Key {key} already exists.")  # Menghindari crash jika key sudah ada

# Fungsi untuk mengecek, menghapus key yang sudah kedaluwarsa, dan menambahkan key baru
def remove_expired_keys_and_generate_new():
    db = get_db()
    now = int(datetime.utcnow().timestamp())  # Waktu sekarang sebagai epoch
    cursor = db.cursor()

    # Menghapus kunci yang sudah kedaluwarsa (lebih dari 24 jam)
    cursor.execute('DELETE FROM keys WHERE created_at < ?', (now - 86400,))  # 86400 detik = 24 jam
    db.commit()

    # Menambahkan kunci baru setelah penghapusan
    for _ in range(100):  # Ganti jumlah sesuai kebutuhan
        key = generate_key()
        add_key(key)

# Menjadwalkan generate 100 key setiap hari pada jam tertentu, misalnya jam 00:00 UTC
def generate_daily_keys():
    db = get_db()
    for _ in range(100):
        key = generate_key()
        add_key(key)

schedule.every().day.at("00:00").do(generate_daily_keys)

# Menjadwalkan pengecekan dan penggantian key yang sudah kedaluwarsa setiap jam
schedule.every().hour.do(remove_expired_keys_and_generate_new)

# Fungsi untuk menjalankan schedule secara terus-menerus di background
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Menjalankan scheduler di thread terpisah
t = threading.Thread(target=run_schedule)
t.start()

# Generate 100 key otomatis saat aplikasi pertama kali dijalankan
with app.app_context():
    generate_daily_keys()

# API untuk mengautentikasi key
@app.route('/api/authenticate', methods=['POST'])
def authenticate_key():
    key = request.json.get('key')
    
    if not key:
        return jsonify({"error": "Key is required"}), 400

    # Cek apakah key ada di database dan belum kedaluwarsa
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT created_at FROM keys WHERE key = ?', (key,))
    result = cursor.fetchone()

    if result:
        # Menangani timestamp sebagai epoch time
        created_at = datetime.utcfromtimestamp(result['created_at'])
        
        if datetime.utcnow() - created_at <= timedelta(hours=24):
            return jsonify({"status": "success", "message": "Key is valid"}), 200
        else:
            return jsonify({"status": "failed", "message": "Key has expired"}), 401
    else:
        return jsonify({"status": "failed", "message": "Invalid key"}), 401

# API untuk mengambil key yang tersedia
@app.route('/api/get_keys', methods=['GET'])
def get_keys():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT key FROM keys')
    keys = cursor.fetchall()
    
    return jsonify([key['key'] for key in keys]), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
