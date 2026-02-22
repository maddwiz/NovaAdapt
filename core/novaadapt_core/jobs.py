from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class JobRecord:
    id: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    """In-memory async job manager for long-running objective execution."""

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def submit(self, fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord(
            id=job_id,
            status="queued",
            created_at=_now_iso(),
        )
        with self._lock:
            self._jobs[job_id] = record

        self._executor.submit(self._run, job_id, fn, *args, **kwargs)
        return job_id

    def _run(self, job_id: str, fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = "running"
            record.started_at = _now_iso()

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                record = self._jobs[job_id]
                record.status = "succeeded"
                record.result = result
                record.finished_at = _now_iso()
        except Exception as exc:  # pragma: no cover - defensive boundary
            with self._lock:
                record = self._jobs[job_id]
                record.status = "failed"
                record.error = str(exc)
                record.finished_at = _now_iso()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            return _serialize(record)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._jobs.values())
        records.sort(key=lambda item: item.created_at, reverse=True)
        return [_serialize(item) for item in records[: max(1, limit)]]

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


def _serialize(record: JobRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "status": record.status,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "result": record.result,
        "error": record.error,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
