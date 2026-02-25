from __future__ import annotations

from pathlib import Path
from typing import Any

from novaadapt_shared import UndoQueue

from .audit_store import AuditStore
from .idempotency_store import IdempotencyStore
from .job_store import JobStore
from .plan_store import PlanStore


def prune_local_state(
    *,
    actions_db_path: Path,
    plans_db_path: Path,
    jobs_db_path: Path,
    idempotency_db_path: Path,
    audit_db_path: Path,
    actions_retention_seconds: int,
    plans_retention_seconds: int,
    jobs_retention_seconds: int,
    idempotency_retention_seconds: int,
    audit_retention_seconds: int,
) -> dict[str, Any]:
    actions_removed = UndoQueue(actions_db_path).prune_older_than(actions_retention_seconds)
    plans_removed = PlanStore(plans_db_path).prune_older_than(plans_retention_seconds)
    jobs_removed = JobStore(jobs_db_path).prune_older_than(jobs_retention_seconds)
    idempotency_removed = IdempotencyStore(
        idempotency_db_path,
        retention_seconds=max(0, int(idempotency_retention_seconds)),
        cleanup_interval_seconds=0.0,
    ).prune_expired()
    audit_removed = AuditStore(
        audit_db_path,
        retention_seconds=max(0, int(audit_retention_seconds)),
        cleanup_interval_seconds=0.0,
    ).prune_expired()

    return {
        "ok": True,
        "removed_total": int(actions_removed + plans_removed + jobs_removed + idempotency_removed + audit_removed),
        "removed": {
            "actions": int(actions_removed),
            "plans": int(plans_removed),
            "jobs": int(jobs_removed),
            "idempotency": int(idempotency_removed),
            "audit": int(audit_removed),
        },
        "retention_seconds": {
            "actions": max(0, int(actions_retention_seconds)),
            "plans": max(0, int(plans_retention_seconds)),
            "jobs": max(0, int(jobs_retention_seconds)),
            "idempotency": max(0, int(idempotency_retention_seconds)),
            "audit": max(0, int(audit_retention_seconds)),
        },
        "paths": {
            "actions": str(Path(actions_db_path).expanduser()),
            "plans": str(Path(plans_db_path).expanduser()),
            "jobs": str(Path(jobs_db_path).expanduser()),
            "idempotency": str(Path(idempotency_db_path).expanduser()),
            "audit": str(Path(audit_db_path).expanduser()),
        },
    }
