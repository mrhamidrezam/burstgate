"""
Persistent, inter-process SQLite storage backend for BurstGate.
Allows multiple worker processes to share rate-limit counters without Redis.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Callable, Optional, Tuple, TypeVar

from burstgate.storage.base import StorageBackend

T = TypeVar("T")


class SQLiteStorage(StorageBackend):
    """
    Zero-dependency multi-process rate limiter storage backed by SQLite in WAL mode.

    Ideal for multi-worker environments (Gunicorn, Uvicorn, Celery, multiprocessing)
    where multiple separate OS processes need synchronized rate limiting without Redis.
    """

    def __init__(
        self,
        db_path: str = "burstgate_limits.sqlite3",
        timeout: float = 10.0,
        cleanup_interval: float = 60.0,
    ) -> None:
        self.db_path = os.path.abspath(db_path)
        self.timeout = float(timeout)
        self._cleanup_interval = float(cleanup_interval)
        self._last_cleanup = time.time()
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                isolation_level=None,  # Autocommit mode, we manage transactions explicitly
            )
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)};")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS burstgate_kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expire_at REAL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_burstgate_expire 
            ON burstgate_kv(expire_at);
            """
        )

    def _purge_expired(self, now: float) -> None:
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM burstgate_kv WHERE expire_at IS NOT NULL AND expire_at <= ?;", (now,))
        except sqlite3.OperationalError:
            pass

    def get(self, key: str) -> Any:
        now = time.time()
        self._purge_expired(now)
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT value, expire_at FROM burstgate_kv WHERE key = ?;",
            (key,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        raw_val, expire_at = row
        if expire_at is not None and expire_at <= now:
            conn.execute("DELETE FROM burstgate_kv WHERE key = ?;", (key,))
            return None
        try:
            return json.loads(raw_val)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        now = time.time()
        self._purge_expired(now)
        expire_at = (now + ttl) if ttl is not None else None
        raw_val = json.dumps(value)
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO burstgate_kv (key, value, expire_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                expire_at = excluded.expire_at;
            """,
            (key, raw_val, expire_at),
        )

    def delete(self, key: str) -> bool:
        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM burstgate_kv WHERE key = ?;", (key,))
        return cursor.rowcount > 0

    def atomic_update(
        self,
        key: str,
        update_fn: Callable[[Any], Tuple[Any, T]],
        default: Any = None,
        ttl: Optional[float] = None,
    ) -> T:
        now = time.time()
        self._purge_expired(now)
        expire_at = (now + ttl) if ttl is not None else None
        conn = self._get_connection()

        # Execute atomic transaction with BEGIN IMMEDIATE
        conn.execute("BEGIN IMMEDIATE;")
        try:
            cursor = conn.execute(
                "SELECT value, expire_at FROM burstgate_kv WHERE key = ?;",
                (key,),
            )
            row = cursor.fetchone()
            curr_val = default
            if row:
                raw_val, row_expire = row
                if row_expire is None or row_expire > now:
                    try:
                        curr_val = json.loads(raw_val)
                    except Exception:
                        curr_val = default

            new_val, result = update_fn(curr_val)
            raw_new_val = json.dumps(new_val)

            conn.execute(
                """
                INSERT INTO burstgate_kv (key, value, expire_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expire_at = excluded.expire_at;
                """,
                (key, raw_new_val, expire_at),
            )
            conn.execute("COMMIT;")
            return result
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def clear(self) -> None:
        conn = self._get_connection()
        conn.execute("DELETE FROM burstgate_kv;")
        self._last_cleanup = time.time()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
