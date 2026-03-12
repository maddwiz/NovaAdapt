from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from novaadapt_shared.sqlite_migrations import SQLiteMigration, apply_sqlite_migrations


class PlanStore:
    """Persists generated action plans for explicit approve/reject workflows."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        sqlite_timeout_seconds: float = 5.0,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".novaadapt" / "plans.db"
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
                        migration_id="plan_store_0001_create_plans",
                        statements=(
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
                                execution_started_at TEXT,
                                reject_reason TEXT,
                                execution_results_json TEXT,
                                action_log_ids_json TEXT,
                                progress_completed INTEGER NOT NULL DEFAULT 0,
                                progress_total INTEGER NOT NULL DEFAULT 0,
                                execution_error TEXT
                            )
                            """,
                        ),
                    ),
                    SQLiteMigration(
                        migration_id="plan_store_0002_add_hot_path_indexes",
                        statements=(
                            """
                            CREATE INDEX IF NOT EXISTS idx_plans_created_at
                            ON plans(created_at DESC)
                            """,
                            """
                            CREATE INDEX IF NOT EXISTS idx_plans_status_updated_at
                            ON plans(status, updated_at)
                            """,
                        ),
                    ),
                    SQLiteMigration(
                        migration_id="plan_store_0003_add_runtime_metadata",
                        statements=(
                            """
                            ALTER TABLE plans ADD COLUMN vote_summary_json TEXT
                            """,
                            """
                            ALTER TABLE plans ADD COLUMN collaboration_json TEXT
                            """,
                            """
                            ALTER TABLE plans ADD COLUMN repair_json TEXT
                            """,
                        ),
                    ),
                ),
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(plans)").fetchall()
            }
            if "execution_started_at" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN execution_started_at TEXT")
            if "progress_completed" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN progress_completed INTEGER NOT NULL DEFAULT 0")
            if "progress_total" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0")
            if "execution_error" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN execution_error TEXT")
            if "vote_summary_json" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN vote_summary_json TEXT")
            if "collaboration_json" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN collaboration_json TEXT")
            if "repair_json" not in columns:
                conn.execute("ALTER TABLE plans ADD COLUMN repair_json TEXT")
            conn.commit()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan_id = payload.get("id") or uuid.uuid4().hex
        now = _now_iso()
        actions = payload.get("actions", [])
        record = {
            "id": plan_id,
            "objective": str(payload["objective"]),
            "strategy": str(payload.get("strategy", "single")),
            "model": payload.get("model"),
            "model_id": payload.get("model_id"),
            "actions": actions,
            "votes": payload.get("votes", {}),
            "vote_summary": payload.get("vote_summary", {}),
            "model_errors": payload.get("model_errors", {}),
            "attempted_models": payload.get("attempted_models", []),
            "collaboration": payload.get("collaboration", {}),
            "status": str(payload.get("status", "pending")),
            "created_at": now,
            "updated_at": now,
            "approved_at": None,
            "rejected_at": None,
            "executed_at": None,
            "execution_started_at": None,
            "reject_reason": None,
            "execution_results": None,
            "action_log_ids": None,
            "progress_completed": int(payload.get("progress_completed", 0)),
            "progress_total": int(payload.get("progress_total", len(actions))),
            "execution_error": None,
            "repair": payload.get("repair"),
        }
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO plans(
                    id, objective, strategy, model, model_id, actions_json, votes_json,
                    vote_summary_json, model_errors_json, attempted_models_json, collaboration_json,
                    status, created_at, updated_at,
                    approved_at, rejected_at, executed_at, execution_started_at, reject_reason,
                    execution_results_json, action_log_ids_json, progress_completed, progress_total,
                    execution_error, repair_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["objective"],
                    record["strategy"],
                    record["model"],
                    record["model_id"],
                    json.dumps(record["actions"]),
                    json.dumps(record["votes"]),
                    json.dumps(record["vote_summary"]),
                    json.dumps(record["model_errors"]),
                    json.dumps(record["attempted_models"]),
                    json.dumps(record["collaboration"]),
                    record["status"],
                    record["created_at"],
                    record["updated_at"],
                    record["approved_at"],
                    record["rejected_at"],
                    record["executed_at"],
                    record["execution_started_at"],
                    record["reject_reason"],
                    None,
                    None,
                    record["progress_completed"],
                    record["progress_total"],
                    record["execution_error"],
                    json.dumps(record["repair"]) if record["repair"] is not None else None,
                ),
            )
            conn.commit()
        return record

    def get(self, plan_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, objective, strategy, model, model_id, actions_json, votes_json,
                       vote_summary_json, model_errors_json, attempted_models_json, collaboration_json,
                       status, created_at, updated_at,
                       approved_at, rejected_at, executed_at, execution_started_at, reject_reason,
                       execution_results_json, action_log_ids_json,
                       progress_completed, progress_total, execution_error, repair_json
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
                       vote_summary_json, model_errors_json, attempted_models_json, collaboration_json,
                       status, created_at, updated_at,
                       approved_at, rejected_at, executed_at, execution_started_at, reject_reason,
                       execution_results_json, action_log_ids_json,
                       progress_completed, progress_total, execution_error, repair_json
                FROM plans
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_executing(self, plan_id: str, total_actions: int) -> dict[str, Any] | None:
        if self.get(plan_id) is None:
            return None
        now = _now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE plans
                SET status = ?,
                    updated_at = ?,
                    approved_at = COALESCE(approved_at, ?),
                    execution_started_at = COALESCE(execution_started_at, ?),
                    progress_completed = ?,
                    progress_total = ?,
                    execution_error = NULL
                WHERE id = ?
                """,
                ("executing", now, now, now, 0, max(0, int(total_actions)), plan_id),
            )
            conn.commit()
        return self.get(plan_id)

    def update_execution_progress(
        self,
        plan_id: str,
        execution_results: list[dict[str, Any]],
        action_log_ids: list[int],
        progress_completed: int,
        progress_total: int,
    ) -> dict[str, Any] | None:
        current = self.get(plan_id)
        if current is None:
            return None
        now = _now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE plans
                SET updated_at = ?,
                    execution_results_json = ?,
                    action_log_ids_json = ?,
                    progress_completed = ?,
                    progress_total = ?
                WHERE id = ?
                """,
                (
                    now,
                    json.dumps(execution_results),
                    json.dumps(action_log_ids),
                    max(0, int(progress_completed)),
                    max(0, int(progress_total)),
                    plan_id,
                ),
            )
            conn.commit()
        return self.get(plan_id)

    def fail_execution(
        self,
        plan_id: str,
        error: str,
        execution_results: list[dict[str, Any]] | None = None,
        action_log_ids: list[int] | None = None,
        progress_completed: int | None = None,
        progress_total: int | None = None,
        repair_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = self.get(plan_id)
        if current is None:
            return None
        now = _now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE plans
                SET status = ?,
                    updated_at = ?,
                    executed_at = ?,
                    execution_results_json = ?,
                    action_log_ids_json = ?,
                    progress_completed = ?,
                    progress_total = ?,
                    execution_error = ?,
                    repair_json = ?
                WHERE id = ?
                """,
                (
                    "failed",
                    now,
                    now,
                    json.dumps(execution_results) if execution_results is not None else json.dumps(current.get("execution_results")),
                    json.dumps(action_log_ids) if action_log_ids is not None else json.dumps(current.get("action_log_ids")),
                    (
                        max(0, int(progress_completed))
                        if progress_completed is not None
                        else int(current.get("progress_completed") or 0)
                    ),
                    (
                        max(0, int(progress_total))
                        if progress_total is not None
                        else int(current.get("progress_total") or 0)
                    ),
                    str(error),
                    (
                        json.dumps(repair_summary)
                        if repair_summary is not None
                        else (json.dumps(current.get("repair")) if current.get("repair") is not None else None)
                    ),
                    plan_id,
                ),
            )
            conn.commit()
        return self.get(plan_id)

    def approve(
        self,
        plan_id: str,
        execution_results: list[dict[str, Any]] | None = None,
        action_log_ids: list[int] | None = None,
        status: str = "approved",
        repair_summary: dict[str, Any] | None = None,
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
                    action_log_ids_json = ?,
                    progress_completed = ?,
                    progress_total = ?,
                    execution_error = NULL,
                    repair_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    now,
                    now if execution_results is not None else current.get("executed_at"),
                    execution_results_json,
                    action_log_ids_json,
                    len(execution_results or []),
                    max(len(current.get("actions") or []), len(execution_results or [])),
                    (
                        json.dumps(repair_summary)
                        if repair_summary is not None
                        else (json.dumps(current.get("repair")) if current.get("repair") is not None else None)
                    ),
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
                    reject_reason = ?,
                    execution_error = NULL
                WHERE id = ?
                """,
                ("rejected", now, now, reason, plan_id),
            )
            conn.commit()
        return self.get(plan_id)

    def prune_older_than(self, older_than_seconds: int) -> int:
        retention = max(0, int(older_than_seconds))
        if retention <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention)
        cutoff_iso = cutoff.isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM plans
                WHERE status IN ('approved', 'executed', 'rejected', 'failed')
                  AND datetime(updated_at) < datetime(?)
                """,
                (cutoff_iso,),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

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
            "vote_summary": _j(row[7], {}),
            "model_errors": _j(row[8], {}),
            "attempted_models": _j(row[9], []),
            "collaboration": _j(row[10], {}),
            "status": row[11],
            "created_at": row[12],
            "updated_at": row[13],
            "approved_at": row[14],
            "rejected_at": row[15],
            "executed_at": row[16],
            "execution_started_at": row[17],
            "reject_reason": row[18],
            "execution_results": _j(row[19], None),
            "action_log_ids": _j(row[20], None),
            "progress_completed": int(row[21] or 0),
            "progress_total": int(row[22] or 0),
            "execution_error": row[23],
            "repair": _j(row[24], None),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
