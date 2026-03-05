from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorkflowRecord:
    workflow_id: str
    status: str
    objective: str
    steps: list[dict[str, Any]]
    context: dict[str, Any]
    created_at: str
    updated_at: str
    last_error: str


class WorkflowStore:
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
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.commit()

    def create(
        self,
        objective: str,
        *,
        steps: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
        workflow_id: str = "",
        status: str = "queued",
    ) -> WorkflowRecord:
        normalized_objective = str(objective or "").strip()
        if not normalized_objective:
            raise ValueError("'objective' is required")
        now = _utc_now()
        wid = str(workflow_id or f"wf-{uuid.uuid4().hex[:16]}")
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO workflows (
                    workflow_id, status, objective, steps_json, context_json, created_at, updated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wid,
                    str(status or "queued"),
                    normalized_objective,
                    json.dumps(list(steps or []), ensure_ascii=True),
                    json.dumps(dict(context or {}), ensure_ascii=True),
                    now,
                    now,
                    "",
                ),
            )
            conn.commit()
        record = self.get(wid)
        if record is None:
            raise RuntimeError(f"workflow create failed: {wid}")
        return record

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        normalized = str(workflow_id or "").strip()
        if not normalized:
            raise ValueError("'workflow_id' is required")
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT workflow_id, status, objective, steps_json, context_json, created_at, updated_at, last_error
                FROM workflows WHERE workflow_id = ?
                """,
                (normalized,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list(self, *, limit: int = 50, status: str = "") -> list[WorkflowRecord]:
        capped = max(1, min(500, int(limit)))
        normalized_status = str(status or "").strip()
        query = (
            """
            SELECT workflow_id, status, objective, steps_json, context_json, created_at, updated_at, last_error
            FROM workflows
            """
        )
        params: tuple[Any, ...] = ()
        if normalized_status:
            query += " WHERE status = ?"
            params = (normalized_status,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, capped)
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update(
        self,
        workflow_id: str,
        *,
        status: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
        last_error: str | None = None,
    ) -> WorkflowRecord | None:
        current = self.get(workflow_id)
        if current is None:
            return None
        new_status = str(status if status is not None else current.status)
        new_steps = list(steps if steps is not None else current.steps)
        new_context = dict(context if context is not None else current.context)
        new_last_error = str(last_error if last_error is not None else current.last_error)
        updated_at = _utc_now()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE workflows
                SET status = ?, steps_json = ?, context_json = ?, updated_at = ?, last_error = ?
                WHERE workflow_id = ?
                """,
                (
                    new_status,
                    json.dumps(new_steps, ensure_ascii=True),
                    json.dumps(new_context, ensure_ascii=True),
                    updated_at,
                    new_last_error,
                    str(workflow_id),
                ),
            )
            conn.commit()
        return self.get(str(workflow_id))

    def _row_to_record(self, row: sqlite3.Row) -> WorkflowRecord:
        steps_raw = row["steps_json"] if "steps_json" in row.keys() else "[]"
        context_raw = row["context_json"] if "context_json" in row.keys() else "{}"
        try:
            steps = json.loads(str(steps_raw))
        except Exception:
            steps = []
        try:
            context = json.loads(str(context_raw))
        except Exception:
            context = {}
        return WorkflowRecord(
            workflow_id=str(row["workflow_id"]),
            status=str(row["status"]),
            objective=str(row["objective"]),
            steps=steps if isinstance(steps, list) else [],
            context=context if isinstance(context, dict) else {},
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_error=str(row["last_error"]),
        )
