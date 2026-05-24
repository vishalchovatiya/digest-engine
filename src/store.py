from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path('data/state.db')


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS digest_runs (
            digest_id TEXT PRIMARY KEY,
            last_run_utc TEXT,
            last_success_utc TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sent_items (
            digest_id TEXT NOT NULL,
            item_url TEXT NOT NULL,
            sent_utc TEXT NOT NULL,
            PRIMARY KEY (digest_id, item_url)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS source_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            digest_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            status TEXT NOT NULL,         -- 'ok' | 'error' | 'empty'
            item_count INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            run_utc TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            digest_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            retailer TEXT NOT NULL,
            url TEXT NOT NULL,
            price_cad REAL,
            currency TEXT,
            observed_utc TEXT NOT NULL
        )
    ''')
    return conn


def get_last_run(digest_id: str) -> datetime | None:
    with get_conn() as conn:
        row = conn.execute('SELECT last_run_utc FROM digest_runs WHERE digest_id = ?', (digest_id,)).fetchone()
    if not row or not row[0]:
        return None
    return datetime.fromisoformat(row[0])


def mark_run(digest_id: str, success: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute('''
            INSERT INTO digest_runs(digest_id, last_run_utc, last_success_utc)
            VALUES (?, ?, ?)
            ON CONFLICT(digest_id) DO UPDATE SET
                last_run_utc = excluded.last_run_utc,
                last_success_utc = CASE WHEN ? THEN excluded.last_success_utc ELSE digest_runs.last_success_utc END
        ''', (digest_id, now, now if success else None, 1 if success else 0))
        conn.commit()


def has_sent(digest_id: str, item_url: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT 1 FROM sent_items WHERE digest_id = ? AND item_url = ?',
            (digest_id, item_url),
        ).fetchone()
    return row is not None


def mark_sent(digest_id: str, item_url: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO sent_items(digest_id, item_url, sent_utc) VALUES (?, ?, ?)',
            (digest_id, item_url, now),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Source health
# ---------------------------------------------------------------------------

def record_source_health(digest_id: str, source_url: str, status: str,
                         item_count: int = 0, duration_ms: int = 0,
                         error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO source_health(digest_id, source_url, status, item_count, duration_ms, error, run_utc) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (digest_id, source_url, status, item_count, duration_ms, error, now),
        )
        conn.commit()


def recent_source_health(digest_id: str | None = None, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        if digest_id:
            rows = conn.execute(
                'SELECT digest_id, source_url, status, item_count, duration_ms, error, run_utc '
                'FROM source_health WHERE digest_id = ? ORDER BY id DESC LIMIT ?',
                (digest_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT digest_id, source_url, status, item_count, duration_ms, error, run_utc '
                'FROM source_health ORDER BY id DESC LIMIT ?',
                (limit,),
            ).fetchall()
    keys = ['digest_id', 'source_url', 'status', 'item_count', 'duration_ms', 'error', 'run_utc']
    return [dict(zip(keys, r)) for r in rows]


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

def get_last_price(digest_id: str, product_id: str, retailer: str, url: str) -> float | None:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT price_cad FROM price_history '
            'WHERE digest_id = ? AND product_id = ? AND retailer = ? AND url = ? '
            'ORDER BY id DESC LIMIT 1',
            (digest_id, product_id, retailer, url),
        ).fetchone()
    if not row:
        return None
    return row[0]


def record_price(digest_id: str, product_id: str, retailer: str, url: str,
                 price_cad: float | None, currency: str = 'CAD') -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO price_history(digest_id, product_id, retailer, url, price_cad, currency, observed_utc) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (digest_id, product_id, retailer, url, price_cad, currency, now),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

def prune(sent_days: int = 30, health_days: int = 60, price_days: int = 180) -> dict[str, int]:
    """Delete state older than the given retention windows. Returns counts."""
    now = datetime.now(timezone.utc)
    cutoffs = {
        'sent_items': (now - timedelta(days=max(sent_days, 30))).isoformat(),
        'source_health': (now - timedelta(days=max(health_days, 30))).isoformat(),
        'price_history': (now - timedelta(days=max(price_days, 30))).isoformat(),
    }
    deleted: dict[str, int] = {}
    with get_conn() as conn:
        c = conn.execute('DELETE FROM sent_items WHERE sent_utc < ?', (cutoffs['sent_items'],))
        deleted['sent_items'] = c.rowcount
        c = conn.execute('DELETE FROM source_health WHERE run_utc < ?', (cutoffs['source_health'],))
        deleted['source_health'] = c.rowcount
        c = conn.execute('DELETE FROM price_history WHERE observed_utc < ?', (cutoffs['price_history'],))
        deleted['price_history'] = c.rowcount
        conn.commit()
    return deleted
