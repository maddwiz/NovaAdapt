from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditStore:
    """SQLite-backed append-only audit event store."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "events.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_events(
                    created_at, category, action, status, request_id, entity_type, entity_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    str(category),
                    str(action),
                    str(status),
                    request_id,
                    entity_type,
                    entity_id,
                    payload_json,
                ),
            )
            conn.commit()
            event_id = int(cur.lastrowid)
        item = self.get(event_id)
        if item is None:
            raise RuntimeError("Failed to read appended audit event")
        return item

    def get(self, event_id: int) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, created_at, category, action, status, request_id, entity_type, entity_id, payload_json
                FROM audit_events
                WHERE id = ?
                """,
                (int(event_id),),
            ).fetchone()
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
        params.append(max(1, int(limit)))
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, created_at, category, action, status, request_id, entity_type, entity_id, payload_json
                FROM audit_events
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def _init(self) -> None:
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
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()


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
