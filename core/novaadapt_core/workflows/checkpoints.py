from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowCheckpointStore:
    def __init__(self, path: str) -> None:
        self.path = str(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                    workflow_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_id, checkpoint_id)
                )
                """
            )
            conn.commit()

    def save(self, workflow_id: str, checkpoint_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_wf = str(workflow_id or "").strip()
        normalized_cp = str(checkpoint_id or "").strip()
        if not normalized_wf:
            raise ValueError("'workflow_id' is required")
        if not normalized_cp:
            raise ValueError("'checkpoint_id' is required")
        record = {
            "workflow_id": normalized_wf,
            "checkpoint_id": normalized_cp,
            "payload": dict(payload or {}),
            "created_at": _utc_now(),
        }
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_checkpoints (workflow_id, checkpoint_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    normalized_wf,
                    normalized_cp,
                    json.dumps(record["payload"], ensure_ascii=True),
                    str(record["created_at"]),
                ),
            )
            conn.commit()
        return record

    def load(self, workflow_id: str, checkpoint_id: str) -> dict[str, Any] | None:
        normalized_wf = str(workflow_id or "").strip()
        normalized_cp = str(checkpoint_id or "").strip()
        if not normalized_wf:
            raise ValueError("'workflow_id' is required")
        if not normalized_cp:
            raise ValueError("'checkpoint_id' is required")
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT workflow_id, checkpoint_id, payload_json, created_at
                FROM workflow_checkpoints
                WHERE workflow_id = ? AND checkpoint_id = ?
                """,
                (normalized_wf, normalized_cp),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def latest(self, workflow_id: str) -> dict[str, Any] | None:
        normalized_wf = str(workflow_id or "").strip()
        if not normalized_wf:
            raise ValueError("'workflow_id' is required")
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT workflow_id, checkpoint_id, payload_json, created_at
                FROM workflow_checkpoints
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized_wf,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list(self, workflow_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        normalized_wf = str(workflow_id or "").strip()
        if not normalized_wf:
            raise ValueError("'workflow_id' is required")
        capped = max(1, min(200, int(limit)))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT workflow_id, checkpoint_id, payload_json, created_at
                FROM workflow_checkpoints
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (normalized_wf, capped),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        payload_raw = row["payload_json"] if "payload_json" in row.keys() else "{}"
        try:
            payload = json.loads(str(payload_raw))
        except Exception:
            payload = {}
        return {
            "workflow_id": str(row["workflow_id"]),
            "checkpoint_id": str(row["checkpoint_id"]),
            "payload": payload if isinstance(payload, dict) else {},
            "created_at": str(row["created_at"]),
        }
