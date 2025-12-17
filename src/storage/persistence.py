import os
import json
import sqlite3
import time
from typing import Dict

class Persistence:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            grade TEXT,
            type TEXT,
            desc TEXT,
            metrics_json TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT,
            side TEXT,
            price REAL,
            stop_loss REAL,
            take_profit REAL,
            notional_usd REAL,
            size_base REAL,
            reason TEXT,
            metrics_json TEXT
        )
        """)
        self.conn.commit()

    def save_signal(self, signal: Dict, platform_metrics: Dict, symbol: str):
        cur = self.conn.cursor()
        ts = int(time.time())
        metrics_json = json.dumps(platform_metrics, ensure_ascii=False)
        cur.execute("""
        INSERT INTO signals (ts, symbol, grade, type, desc, metrics_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (ts, symbol, signal.get('grade'), signal.get('type'), signal.get('desc'), metrics_json))
        self.conn.commit()

    def save_recommendation(self, rec: Dict, platform_metrics: Dict):
        cur = self.conn.cursor()
        ts = int(time.time())
        metrics_json = json.dumps(platform_metrics, ensure_ascii=False)
        cur.execute("""
        INSERT INTO recommendations (ts, symbol, action, side, price, stop_loss, take_profit, notional_usd, size_base, reason, metrics_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts,
            rec.get('symbol'),
            rec.get('action'),
            rec.get('side'),
            rec.get('price'),
            rec.get('stop_loss'),
            rec.get('take_profit'),
            rec.get('notional_usd'),
            rec.get('size_base'),
            rec.get('reason'),
            metrics_json
        ))
        self.conn.commit()
