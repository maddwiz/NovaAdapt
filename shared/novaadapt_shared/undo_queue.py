from __future__ import annotations

import json
import sqlite3
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

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    undone INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def record(self, action: dict[str, Any], status: str) -> int:
        payload = json.dumps(action, separators=(",", ":"))
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO action_log(action_json, status) VALUES (?, ?)",
                (payload, status),
            )
            return int(cursor.lastrowid)

    def mark_undone(self, action_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE action_log SET undone = 1 WHERE id = ?", (action_id,))

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, action_json, status, created_at, undone
                FROM action_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "action": json.loads(row[1]),
                    "status": row[2],
                    "created_at": row[3],
                    "undone": bool(row[4]),
                }
            )
        return result
