from __future__ import annotations

import inspect
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .job_store import JobStore


@dataclass
class JobRecord:
    id: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False


class JobManager:
    """Async job manager with optional SQLite-backed persistence."""

    def __init__(self, max_workers: int = 4, store: JobStore | None = None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._futures: dict[str, Future[None]] = {}
        self._store = store

        if self._store is not None:
            for row in self._store.list(limit=500):
                self._jobs[row["id"]] = JobRecord(
                    id=row["id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    started_at=row.get("started_at"),
                    finished_at=row.get("finished_at"),
                    result=row.get("result"),
                    error=row.get("error"),
                    cancel_requested=bool(row.get("cancel_requested")),
                )

    def submit(self, fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord(
            id=job_id,
            status="queued",
            created_at=_now_iso(),
        )
        with self._lock:
            self._jobs[job_id] = record
            self._persist(record)

        future = self._executor.submit(self._run, job_id, fn, *args, **kwargs)
        with self._lock:
            self._futures[job_id] = future
        return job_id

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None and self._store is not None:
                persisted = self._store.get(job_id)
                if persisted is not None:
                    record = JobRecord(
                        id=persisted["id"],
                        status=persisted["status"],
                        created_at=persisted["created_at"],
                        started_at=persisted.get("started_at"),
                        finished_at=persisted.get("finished_at"),
                        result=persisted.get("result"),
                        error=persisted.get("error"),
                        cancel_requested=bool(persisted.get("cancel_requested")),
                    )
                    self._jobs[job_id] = record

            if record is None:
                return None

            future = self._futures.get(job_id)
            if record.status in {"succeeded", "failed", "canceled"}:
                return {
                    "id": job_id,
                    "canceled": False,
                    "status": record.status,
                    "message": "Job already finished",
                }

            canceled = bool(future and future.cancel())
            if canceled:
                record.status = "canceled"
                record.cancel_requested = True
                record.finished_at = _now_iso()
                self._persist(record)
                return {
                    "id": job_id,
                    "canceled": True,
                    "status": "canceled",
                    "message": "Job canceled before execution",
                }

            record.cancel_requested = True
            self._persist(record)
            return {
                "id": job_id,
                "canceled": False,
                "status": record.status,
                "message": "Job already running; cancellation requested",
            }

    def _run(self, job_id: str, fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> None:
        with self._lock:
            record = self._jobs[job_id]
            if record.status == "canceled":
                return
            record.status = "running"
            record.started_at = _now_iso()
            self._persist(record)

        call_kwargs = dict(kwargs)
        if "cancel_requested" not in call_kwargs:
            try:
                signature = inspect.signature(fn)
                if "cancel_requested" in signature.parameters:
                    call_kwargs["cancel_requested"] = lambda: self._is_cancel_requested(job_id)
            except (TypeError, ValueError):  # pragma: no cover - non-introspectable callables
                pass

        try:
            result = fn(*args, **call_kwargs)
            with self._lock:
                record = self._jobs[job_id]
                if record.status == "canceled" or record.cancel_requested:
                    record.status = "canceled"
                    record.result = result
                    record.error = record.error or "Canceled by operator"
                    record.finished_at = _now_iso()
                    self._persist(record)
                    return
                record.status = "succeeded"
                record.result = result
                record.finished_at = _now_iso()
                self._persist(record)
        except Exception as exc:  # pragma: no cover - defensive boundary
            with self._lock:
                record = self._jobs[job_id]
                if record.status == "canceled" or record.cancel_requested:
                    record.status = "canceled"
                    record.error = str(exc) or "Canceled by operator"
                    record.finished_at = _now_iso()
                    self._persist(record)
                    return
                record.status = "failed"
                record.error = str(exc)
                record.finished_at = _now_iso()
                self._persist(record)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is not None:
                return _serialize(record)

        if self._store is not None:
            return self._store.get(job_id)
        return None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._jobs.values())
        if records:
            records.sort(key=lambda item: item.created_at, reverse=True)
            return [_serialize(item) for item in records[: max(1, limit)]]

        if self._store is not None:
            return self._store.list(limit=limit)
        return []

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def _persist(self, record: JobRecord) -> None:
        if self._store is not None:
            self._store.upsert(_serialize(record))

    def _is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            record = self._jobs.get(job_id)
            return bool(record and record.cancel_requested)


def _serialize(record: JobRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "result": record.result,
        "error": record.error,
        "cancel_requested": record.cancel_requested,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
