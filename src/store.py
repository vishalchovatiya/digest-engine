from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

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
