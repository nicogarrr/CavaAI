import sqlite3
import json
import time

DB_NAME = "cache.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS financials (
            symbol TEXT,
            data_type TEXT,
            data TEXT,
            timestamp REAL,
            PRIMARY KEY (symbol, data_type)
        )
    ''')
    conn.commit()
    conn.close()

def get_cached_data(symbol: str, data_type: str, max_age_seconds: int = 86400):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT data, timestamp FROM financials WHERE symbol=? AND data_type=?", (symbol, data_type))
        result = c.fetchone()
        conn.close()
        if result:
            data_str, timestamp = result
            if time.time() - timestamp < max_age_seconds:
                return json.loads(data_str)
    except Exception as e:
        print(f"Cache error: {e}")
    return None

def save_to_cache(symbol: str, data_type: str, data):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO financials VALUES (?, ?, ?, ?)",
                  (symbol, data_type, json.dumps(data), time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Cache write error: {e}")

init_db()
