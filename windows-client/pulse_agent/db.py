"""
Local sqlite store shared by PulseService (Session 0) and PulseHelper (the
logged-in user's session) — same role as android-app's Db.java: a small
key/value config table plus per-kind upload queues that get drained by the
service's sync loop and marked synced on success.

WAL mode matters here specifically because this file is opened by two
separate OS processes running as two different Windows accounts (SYSTEM and
whichever user is logged in) at the same time, not just two threads in one
process — WAL lets a writer and a reader proceed without blocking each
other anywhere near as often as the default rollback journal would.
"""
import sqlite3
import threading
import time

from . import paths

_lock = threading.Lock()
_conn = None


def _connect():
    paths.ensure_dirs()
    conn = sqlite3.connect(paths.DB_PATH, timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=10000')
    return conn


def get_conn():
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = _connect()
                _init_schema(_conn)
    return _conn


def _init_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS usage_q (
            id INTEGER PRIMARY KEY AUTOINCREMENT, package TEXT, label TEXT,
            start_ts INTEGER, end_ts INTEGER, synced INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS browse_q (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, source TEXT,
            app TEXT, url TEXT, domain TEXT, title TEXT, synced INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS data_q (
            id INTEGER PRIMARY KEY AUTOINCREMENT, package TEXT, label TEXT,
            ts INTEGER, rx INTEGER, tx INTEGER, transport TEXT, synced INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_usage_sync ON usage_q(synced);
        CREATE INDEX IF NOT EXISTS idx_browse_sync ON browse_q(synced);
        CREATE INDEX IF NOT EXISTS idx_data_sync ON data_q(synced);
    """)
    conn.commit()


# ── config kv ────────────────────────────────────────────────────────────
def get_str(k, default=None):
    row = get_conn().execute('SELECT v FROM kv WHERE k=?', (k,)).fetchone()
    return row[0] if row else default


def get_bool(k, default=False):
    return get_str(k, '1' if default else '0') == '1'


def put(k, v):
    conn = get_conn()
    conn.execute('INSERT INTO kv(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, str(v)))
    conn.commit()


def put_bool(k, v):
    put(k, '1' if v else '0')


# ── queues ───────────────────────────────────────────────────────────────
def add_usage(package, label, start_ts, end_ts):
    conn = get_conn()
    conn.execute('INSERT INTO usage_q(package, label, start_ts, end_ts) VALUES (?, ?, ?, ?)',
                 (package, label, start_ts, end_ts))
    conn.commit()


def add_browse(ts, source, app, url, domain, title):
    conn = get_conn()
    conn.execute('INSERT INTO browse_q(ts, source, app, url, domain, title) VALUES (?, ?, ?, ?, ?, ?)',
                 (ts, source, app, url, domain, title))
    conn.commit()


def add_data_usage(package, label, ts, rx, tx, transport=''):
    conn = get_conn()
    conn.execute('INSERT INTO data_q(package, label, ts, rx, tx, transport) VALUES (?, ?, ?, ?, ?, ?)',
                 (package, label, ts, rx, tx, transport))
    conn.commit()


def pending(table, limit=500):
    cols = {
        'usage_q': 'id, package, label, start_ts, end_ts',
        'browse_q': 'id, ts, source, app, url, domain, title',
        'data_q': 'id, package, label, ts, rx, tx, transport',
    }[table]
    cur = get_conn().execute(f'SELECT {cols} FROM {table} WHERE synced=0 ORDER BY id LIMIT ?', (limit,))
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def mark_synced(table, ids):
    if not ids:
        return
    conn = get_conn()
    qmarks = ','.join('?' * len(ids))
    conn.execute(f'UPDATE {table} SET synced=1 WHERE id IN ({qmarks})', ids)
    conn.commit()
    # Keep the queue tables from growing forever once rows are confirmed sent.
    conn.execute(f'DELETE FROM {table} WHERE synced=1 AND id NOT IN '
                 f'(SELECT id FROM {table} WHERE synced=1 ORDER BY id DESC LIMIT 200)')
    conn.commit()


def now_ms():
    return int(time.time() * 1000)
