from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value)).astimezone(timezone.utc)


@dataclass
class JobRecord:
    job_id: str
    status: str
    payload: dict[str, Any]
    workspace_id: str
    profile_name: str
    reply_to: dict[str, Any]
    attempts: int
    next_retry_at: str
    created_at: str
    updated_at: str
    parent_job_id: str


class GatewayJobQueue:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  job_id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  workspace_id TEXT NOT NULL,
                  profile_name TEXT NOT NULL,
                  reply_to_json TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  next_retry_at TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  parent_job_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deliveries (
                  job_id TEXT NOT NULL,
                  connector TEXT NOT NULL,
                  address TEXT NOT NULL,
                  token TEXT NOT NULL,
                  status TEXT NOT NULL,
                  last_error TEXT NOT NULL DEFAULT '',
                  last_attempt_at TEXT NOT NULL DEFAULT '',
                  PRIMARY KEY(job_id, connector, address)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_retry ON jobs(status, next_retry_at)")
            conn.commit()

    def enqueue(
        self,
        payload: dict[str, Any],
        *,
        job_id: str = "",
        workspace_id: str = "default",
        profile_name: str = "unleashed_local",
        reply_to: dict[str, Any] | None = None,
        parent_job_id: str = "",
    ) -> str:
        resolved_job_id = str(job_id or uuid.uuid4())
        now = _to_ts(_utc_now())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                  job_id, status, payload_json, workspace_id, profile_name,
                  reply_to_json, attempts, next_retry_at, created_at, updated_at, parent_job_id
                ) VALUES (?, 'queued', ?, ?, ?, ?, 0, '', ?, ?, ?)
                """,
                (
                    resolved_job_id,
                    json.dumps(payload, ensure_ascii=True, default=str),
                    str(workspace_id or "default"),
                    str(profile_name or "unleashed_local"),
                    json.dumps(reply_to if isinstance(reply_to, dict) else {}, ensure_ascii=True, default=str),
                    now,
                    now,
                    str(parent_job_id or ""),
                ),
            )
            conn.commit()
        return resolved_job_id

    def claim_next(self, *, now: datetime | None = None) -> JobRecord | None:
        current = now or _utc_now()
        now_ts = _to_ts(current)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE
                  status = 'queued'
                  OR (status = 'retry_wait' AND next_retry_at != '' AND next_retry_at <= ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (now_ts,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET status='running', updated_at=? WHERE job_id=?",
                (now_ts, str(row["job_id"])),
            )
            conn.commit()
            payload = self._row_to_job(
                {
                    **dict(row),
                    "status": "running",
                    "updated_at": now_ts,
                }
            )
            return payload

    def mark_done(self, job_id: str) -> None:
        now = _to_ts(_utc_now())
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status='done', updated_at=? WHERE job_id=?",
                (now, str(job_id)),
            )
            conn.commit()

    def mark_failed(
        self,
        job_id: str,
        *,
        retry_delay_seconds: float = 10.0,
        max_attempts: int = 3,
    ) -> str:
        now = _utc_now()
        now_ts = _to_ts(now)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempts FROM jobs WHERE job_id=? LIMIT 1",
                (str(job_id),),
            ).fetchone()
            if row is None:
                return "missing"
            attempts = int(row["attempts"] or 0) + 1
            if attempts >= max(1, int(max_attempts)):
                status = "failed"
                next_retry_at = ""
            else:
                status = "retry_wait"
                next_retry_at = _to_ts(now + timedelta(seconds=max(1.0, float(retry_delay_seconds))))
            conn.execute(
                """
                UPDATE jobs
                SET status=?, attempts=?, next_retry_at=?, updated_at=?
                WHERE job_id=?
                """,
                (status, attempts, next_retry_at, now_ts, str(job_id)),
            )
            conn.commit()
            return status

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=? LIMIT 1", (str(job_id),)).fetchone()
            if row is None:
                return None
            return self._row_to_job(dict(row))

    def upsert_delivery(
        self,
        *,
        job_id: str,
        connector: str,
        address: str,
        token: str,
        status: str = "pending",
        last_error: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO deliveries (job_id, connector, address, token, status, last_error, last_attempt_at)
                VALUES (?, ?, ?, ?, ?, ?, '')
                ON CONFLICT(job_id, connector, address)
                DO UPDATE SET token=excluded.token, status=excluded.status, last_error=excluded.last_error
                """,
                (
                    str(job_id),
                    str(connector),
                    str(address),
                    str(token),
                    str(status),
                    str(last_error or ""),
                ),
            )
            conn.commit()

    def list_pending_deliveries(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM deliveries
                WHERE job_id=? AND status IN ('pending', 'failed')
                ORDER BY connector, address
                """,
                (str(job_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_delivery(self, *, job_id: str, connector: str, address: str, status: str, last_error: str = "") -> None:
        now_ts = _to_ts(_utc_now())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE deliveries
                SET status=?, last_error=?, last_attempt_at=?
                WHERE job_id=? AND connector=? AND address=?
                """,
                (
                    str(status),
                    str(last_error or ""),
                    now_ts,
                    str(job_id),
                    str(connector),
                    str(address),
                ),
            )
            conn.commit()

    @staticmethod
    def _row_to_job(row: dict[str, Any]) -> JobRecord:
        payload_raw = row.get("payload_json")
        payload = {}
        if isinstance(payload_raw, str) and payload_raw.strip():
            try:
                parsed = json.loads(payload_raw)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        reply_raw = row.get("reply_to_json")
        reply_to = {}
        if isinstance(reply_raw, str) and reply_raw.strip():
            try:
                parsed = json.loads(reply_raw)
                if isinstance(parsed, dict):
                    reply_to = parsed
            except Exception:
                reply_to = {}
        return JobRecord(
            job_id=str(row.get("job_id", "")),
            status=str(row.get("status", "")),
            payload=payload,
            workspace_id=str(row.get("workspace_id", "default") or "default"),
            profile_name=str(row.get("profile_name", "unleashed_local") or "unleashed_local"),
            reply_to=reply_to,
            attempts=int(row.get("attempts", 0) or 0),
            next_retry_at=str(row.get("next_retry_at", "") or ""),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
            parent_job_id=str(row.get("parent_job_id", "") or ""),
        )
