from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class JobStore:
    """Persists async job records in SQLite for restart-safe history."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "jobs.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init(self) -> None:
        with self._connection() as conn:
            conn.execute(
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
                """
            )
            conn.commit()

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
