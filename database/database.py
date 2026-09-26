import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("SHOPWISE_DB", BASE_DIR / "shopwise.db"))

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        brand TEXT,
        category TEXT,
        image_url TEXT,
        mrp REAL,
        average_price REAL,
        lowest_price REAL,
        tracked_days INTEGER DEFAULT 0,
        history_url TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        retailer TEXT NOT NULL,
        price REAL NOT NULL,
        url TEXT NOT NULL,
        currency TEXT DEFAULT 'INR',
        available INTEGER DEFAULT 1,
        observed_at TEXT NOT NULL,
        UNIQUE(product_id, retailer)
    );

    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        retailer TEXT NOT NULL,
        price REAL NOT NULL,
        observed_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_history_product_time
    ON price_history(product_id, observed_at);

    CREATE TABLE IF NOT EXISTS sync_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        retailer TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        message TEXT
    );
    """)
    conn.commit()
    conn.close()
