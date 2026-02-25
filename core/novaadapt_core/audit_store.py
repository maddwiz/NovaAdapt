from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class AuditStore:
    """SQLite-backed append-only audit event store."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 0.02,
        sqlite_timeout_seconds: float = 5.0,
        retention_seconds: int = 30 * 24 * 60 * 60,
        cleanup_interval_seconds: float = 60.0,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "events.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.sqlite_timeout_seconds = max(0.1, float(sqlite_timeout_seconds))
        self.retention_seconds = max(0, int(retention_seconds))
        self.cleanup_interval_seconds = max(0.0, float(cleanup_interval_seconds))
        self._cleanup_lock = threading.Lock()
        self._last_cleanup_monotonic = 0.0
        self._init()

    def append(
        self,
        *,
        category: str,
        action: str,
        status: str,
        request_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        payload_json = json.dumps(payload) if payload is not None else None
        event_id = self._run_with_retry(
            lambda: self._append_once(
                now=now,
                category=str(category),
                action=str(action),
                status=str(status),
                request_id=request_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )
        item = self.get(event_id)
        if item is None:
            raise RuntimeError("Failed to read appended audit event")
        return item

    def get(self, event_id: int) -> dict[str, Any] | None:
        row = self._run_with_retry(lambda: self._get_row(int(event_id)))
        if row is None:
            return None
        return _row_to_dict(row)

    def list(
        self,
        *,
        limit: int = 100,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if since_id is not None:
            clauses.append("id > ?")
            params.append(int(since_id))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_params = tuple([*params, max(1, int(limit))])
        rows = self._run_with_retry(
            lambda: self._list_rows(where_sql=where_sql, params=query_params),
        )
        return [_row_to_dict(row) for row in rows]

    def prune_expired(self) -> int:
        return self._run_with_retry(self._prune_expired_once)

    def _init(self) -> None:
        self._run_with_retry(self._init_once)

    def _init_once(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_id TEXT,
                    entity_type TEXT,
                    entity_id TEXT,
                    payload_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_category_id
                ON audit_events(category, id DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_entity_type_entity_id_id
                ON audit_events(entity_type, entity_id, id DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
                ON audit_events(created_at)
                """
            )
            conn.commit()

    def _append_once(
        self,
        *,
        now: str,
        category: str,
        action: str,
        status: str,
        request_id: str | None,
        entity_type: str | None,
        entity_id: str | None,
        payload_json: str | None,
    ) -> int:
        with self._connection() as conn:
            self._cleanup_expired_locked(conn)
            cur = conn.execute(
                """
                INSERT INTO audit_events(
                    created_at, category, action, status, request_id, entity_type, entity_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    category,
                    action,
                    status,
                    request_id,
                    entity_type,
                    entity_id,
                    payload_json,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _prune_expired_once(self) -> int:
        with self._connection() as conn:
            removed = self._cleanup_expired_locked(conn, force=True)
            if removed > 0:
                conn.commit()
            return removed

    def _get_row(self, event_id: int) -> tuple[Any, ...] | None:
        with self._connection() as conn:
            return conn.execute(
                """
                SELECT id, created_at, category, action, status, request_id, entity_type, entity_id, payload_json
                FROM audit_events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()

    def _list_rows(self, *, where_sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        with self._connection() as conn:
            return conn.execute(
                f"""
                SELECT id, created_at, category, action, status, request_id, entity_type, entity_id, payload_json
                FROM audit_events
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

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

    def _run_with_retry(self, operation: Callable[[], T]) -> T:
        for attempt in range(self.retry_attempts):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if not _is_retryable_sqlite_error(exc) or attempt >= self.retry_attempts - 1:
                    raise
                delay = self.retry_backoff_seconds * (2**attempt)
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError("sqlite retry loop exhausted unexpectedly")

    def _cleanup_expired_locked(self, conn: sqlite3.Connection, *, force: bool = False) -> int:
        if self.retention_seconds <= 0:
            return 0

        now_monotonic = time.monotonic()
        with self._cleanup_lock:
            if not force and self.cleanup_interval_seconds > 0:
                if (now_monotonic - self._last_cleanup_monotonic) < self.cleanup_interval_seconds:
                    return 0
            self._last_cleanup_monotonic = now_monotonic

        cutoff = datetime.fromtimestamp(time.time() - self.retention_seconds, timezone.utc).isoformat()
        cursor = conn.execute("DELETE FROM audit_events WHERE created_at < ?", (cutoff,))
        return int(cursor.rowcount or 0)


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "created_at": row[1],
        "category": row[2],
        "action": row[3],
        "status": row[4],
        "request_id": row[5],
        "entity_type": row[6],
        "entity_id": row[7],
        "payload": json.loads(row[8]) if row[8] is not None else None,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_retryable_sqlite_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).strip().lower()
    if not message:
        return False
    retryable_fragments = (
        "database is locked",
        "database is busy",
        "disk i/o error",
        "database schema is locked",
        "unable to open database file",
    )
    return any(fragment in message for fragment in retryable_fragments)
