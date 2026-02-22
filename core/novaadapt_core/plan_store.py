from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PlanStore:
    """Persists generated action plans for explicit approve/reject workflows."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "plans.db"
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
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    model TEXT,
                    model_id TEXT,
                    actions_json TEXT NOT NULL,
                    votes_json TEXT,
                    model_errors_json TEXT,
                    attempted_models_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    rejected_at TEXT,
                    executed_at TEXT,
                    reject_reason TEXT,
                    execution_results_json TEXT,
                    action_log_ids_json TEXT
                )
                """
            )
            conn.commit()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan_id = payload.get("id") or uuid.uuid4().hex
        now = _now_iso()
        record = {
            "id": plan_id,
            "objective": str(payload["objective"]),
            "strategy": str(payload.get("strategy", "single")),
            "model": payload.get("model"),
            "model_id": payload.get("model_id"),
            "actions": payload.get("actions", []),
            "votes": payload.get("votes", {}),
            "model_errors": payload.get("model_errors", {}),
            "attempted_models": payload.get("attempted_models", []),
            "status": str(payload.get("status", "pending")),
            "created_at": now,
            "updated_at": now,
            "approved_at": None,
            "rejected_at": None,
            "executed_at": None,
            "reject_reason": None,
            "execution_results": None,
            "action_log_ids": None,
        }
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO plans(
                    id, objective, strategy, model, model_id, actions_json, votes_json,
                    model_errors_json, attempted_models_json, status, created_at, updated_at,
                    approved_at, rejected_at, executed_at, reject_reason,
                    execution_results_json, action_log_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["objective"],
                    record["strategy"],
                    record["model"],
                    record["model_id"],
                    json.dumps(record["actions"]),
                    json.dumps(record["votes"]),
                    json.dumps(record["model_errors"]),
                    json.dumps(record["attempted_models"]),
                    record["status"],
                    record["created_at"],
                    record["updated_at"],
                    record["approved_at"],
                    record["rejected_at"],
                    record["executed_at"],
                    record["reject_reason"],
                    None,
                    None,
                ),
            )
            conn.commit()
        return record

    def get(self, plan_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, objective, strategy, model, model_id, actions_json, votes_json,
                       model_errors_json, attempted_models_json, status, created_at, updated_at,
                       approved_at, rejected_at, executed_at, reject_reason,
                       execution_results_json, action_log_ids_json
                FROM plans
                WHERE id = ?
                """,
                (plan_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, objective, strategy, model, model_id, actions_json, votes_json,
                       model_errors_json, attempted_models_json, status, created_at, updated_at,
                       approved_at, rejected_at, executed_at, reject_reason,
                       execution_results_json, action_log_ids_json
                FROM plans
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def approve(
        self,
        plan_id: str,
        execution_results: list[dict[str, Any]] | None = None,
        action_log_ids: list[int] | None = None,
        status: str = "approved",
    ) -> dict[str, Any] | None:
        current = self.get(plan_id)
        if current is None:
            return None

        now = _now_iso()
        execution_results_json = (
            json.dumps(execution_results)
            if execution_results is not None
            else json.dumps(current.get("execution_results"))
        )
        action_log_ids_json = (
            json.dumps(action_log_ids) if action_log_ids is not None else json.dumps(current.get("action_log_ids"))
        )

        with self._connection() as conn:
            conn.execute(
                """
                UPDATE plans
                SET status = ?,
                    updated_at = ?,
                    approved_at = COALESCE(approved_at, ?),
                    executed_at = ?,
                    execution_results_json = ?,
                    action_log_ids_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    now,
                    now if execution_results is not None else current.get("executed_at"),
                    execution_results_json,
                    action_log_ids_json,
                    plan_id,
                ),
            )
            conn.commit()
        return self.get(plan_id)

    def reject(self, plan_id: str, reason: str | None = None) -> dict[str, Any] | None:
        if self.get(plan_id) is None:
            return None
        now = _now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE plans
                SET status = ?,
                    updated_at = ?,
                    rejected_at = ?,
                    reject_reason = ?
                WHERE id = ?
                """,
                ("rejected", now, now, reason, plan_id),
            )
            conn.commit()
        return self.get(plan_id)

    @staticmethod
    def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        def _j(item: Any, fallback: Any) -> Any:
            return json.loads(item) if item is not None else fallback

        return {
            "id": row[0],
            "objective": row[1],
            "strategy": row[2],
            "model": row[3],
            "model_id": row[4],
            "actions": _j(row[5], []),
            "votes": _j(row[6], {}),
            "model_errors": _j(row[7], {}),
            "attempted_models": _j(row[8], []),
            "status": row[9],
            "created_at": row[10],
            "updated_at": row[11],
            "approved_at": row[12],
            "rejected_at": row[13],
            "executed_at": row[14],
            "reject_reason": row[15],
            "execution_results": _j(row[16], None),
            "action_log_ids": _j(row[17], None),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
