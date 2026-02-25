from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from novaadapt_shared.sqlite_migrations import SQLiteMigration, apply_sqlite_migrations


class JobStore:
    """Persists async job records in SQLite for restart-safe history."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        sqlite_timeout_seconds: float = 5.0,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "jobs.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_timeout_seconds = max(0.1, float(sqlite_timeout_seconds))
        self._init()

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

    def _init(self) -> None:
        with self._connection() as conn:
            apply_sqlite_migrations(
                conn,
                (
                    SQLiteMigration(
                        migration_id="job_store_0001_create_async_jobs",
                        statements=(
                            """
                            CREATE TABLE IF NOT EXISTS async_jobs (
                                id TEXT PRIMARY KEY,
                                status TEXT NOT NULL,
                                created_at TEXT NOT NULL,
                                started_at TEXT,
                                finished_at TEXT,
                                result_json TEXT,
                                error TEXT,
                                cancel_requested INTEGER NOT NULL DEFAULT 0
                            )
                            """,
                        ),
                    ),
                    SQLiteMigration(
                        migration_id="job_store_0002_add_hot_path_indexes",
                        statements=(
                            """
                            CREATE INDEX IF NOT EXISTS idx_async_jobs_created_at
                            ON async_jobs(created_at DESC)
                            """,
                            """
                            CREATE INDEX IF NOT EXISTS idx_async_jobs_status_finished_at
                            ON async_jobs(status, finished_at)
                            """,
                        ),
                    ),
                ),
            )

    def upsert(self, record: dict[str, Any]) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO async_jobs(
                    id, status, created_at, started_at, finished_at, result_json, error, cancel_requested
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    result_json=excluded.result_json,
                    error=excluded.error,
                    cancel_requested=excluded.cancel_requested
                """,
                (
                    record["id"],
                    record["status"],
                    record["created_at"],
                    record.get("started_at"),
                    record.get("finished_at"),
                    json.dumps(record.get("result")) if record.get("result") is not None else None,
                    record.get("error"),
                    1 if record.get("cancel_requested") else 0,
                ),
            )
            conn.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, status, created_at, started_at, finished_at, result_json, error, cancel_requested
                FROM async_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, status, created_at, started_at, finished_at, result_json, error, cancel_requested
                FROM async_jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def prune_older_than(self, older_than_seconds: int) -> int:
        retention = max(0, int(older_than_seconds))
        if retention <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention)
        cutoff_iso = cutoff.isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM async_jobs
                WHERE status IN ('succeeded', 'failed', 'canceled')
                  AND datetime(COALESCE(finished_at, created_at)) < datetime(?)
                """,
                (cutoff_iso,),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    @staticmethod
    def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        result_json = row[5]
        return {
            "id": row[0],
            "status": row[1],
            "created_at": row[2],
            "started_at": row[3],
            "finished_at": row[4],
            "result": json.loads(result_json) if result_json else None,
            "error": row[6],
            "cancel_requested": bool(row[7]),
        }
