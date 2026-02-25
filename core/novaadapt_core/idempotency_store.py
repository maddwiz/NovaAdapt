from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class IdempotencyStore:
    """SQLite-backed idempotency key store for mutating API routes."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        sqlite_timeout_seconds: float = 5.0,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "idempotency.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_timeout_seconds = max(0.1, float(sqlite_timeout_seconds))
        self._lock = threading.Lock()
        self._init()

    def begin(
        self,
        key: str,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        payload_hash = _hash_payload(payload)
        now = _now_iso()
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT payload_hash, status, status_code, response_json
                FROM idempotency_entries
                WHERE key = ? AND method = ? AND path = ?
                """,
                (key, method, path),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO idempotency_entries(
                        key, method, path, payload_hash, status, status_code, response_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (key, method, path, payload_hash, "in_progress", None, None, now, now),
                )
                conn.commit()
                return "new", None

            existing_hash, status, status_code, response_json = row
            if existing_hash != payload_hash:
                return "conflict", {"error": "Idempotency key reused with different payload"}
            if status == "completed":
                response_payload: Any = {}
                if response_json:
                    response_payload = json.loads(response_json)
                return "replay", {"status_code": int(status_code or 200), "payload": response_payload}
            return "in_progress", {"error": "Request with this idempotency key is already in progress"}

    def complete(
        self,
        key: str,
        method: str,
        path: str,
        status_code: int,
        payload: Any,
    ) -> None:
        now = _now_iso()
        encoded = json.dumps(payload, separators=(",", ":"))
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                UPDATE idempotency_entries
                SET status = ?,
                    status_code = ?,
                    response_json = ?,
                    updated_at = ?
                WHERE key = ? AND method = ? AND path = ?
                """,
                ("completed", int(status_code), encoded, now, key, method, path),
            )
            conn.commit()

    def clear(self, key: str, method: str, path: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "DELETE FROM idempotency_entries WHERE key = ? AND method = ? AND path = ?",
                (key, method, path),
            )
            conn.commit()

    def _init(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_entries (
                    key TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_code INTEGER,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (key, method, path)
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.sqlite_timeout_seconds)
        conn.execute(f"PRAGMA busy_timeout={int(self.sqlite_timeout_seconds * 1000)}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
