from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class UndoQueue:
    """Simple local action log for previews, execution tracking, and undo workflows."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "actions.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_json TEXT NOT NULL,
                    undo_action_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    undone INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(action_log)").fetchall()
            }
            if "undo_action_json" not in columns:
                conn.execute("ALTER TABLE action_log ADD COLUMN undo_action_json TEXT")
            conn.commit()

    def record(
        self,
        action: dict[str, Any],
        status: str,
        undo_action: dict[str, Any] | None = None,
    ) -> int:
        payload = json.dumps(action, separators=(",", ":"))
        undo_payload = (
            json.dumps(undo_action, separators=(",", ":"))
            if undo_action is not None
            else None
        )
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO action_log(action_json, undo_action_json, status) VALUES (?, ?, ?)",
                (payload, undo_payload, status),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def mark_undone(self, action_id: int) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE action_log SET undone = 1 WHERE id = ? AND undone = 0",
                (action_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get(self, action_id: int) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, action_json, undo_action_json, status, created_at, undone
                FROM action_log
                WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def latest_pending(self) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, action_json, undo_action_json, status, created_at, undone
                FROM action_log
                WHERE undone = 0
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, action_json, undo_action_json, status, created_at, undone
                FROM action_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: tuple[Any, ...]) -> dict[str, Any]:
        undo_payload = row[2]
        return {
            "id": row[0],
            "action": json.loads(row[1]),
            "undo_action": json.loads(undo_payload) if undo_payload else None,
            "status": row[3],
            "created_at": row[4],
            "undone": bool(row[5]),
        }
