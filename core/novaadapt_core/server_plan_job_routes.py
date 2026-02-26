from __future__ import annotations

from typing import Callable

from .jobs import JobManager
from .service import NovaAdaptService


def get_jobs(
    handler,
    job_manager: JobManager,
    query_single: Callable[[dict[str, list[str]], str], str | None],
    query: dict[str, list[str]],
) -> int:
    limit = int(query_single(query, "limit") or 50)
    handler._send_json(200, job_manager.list(limit=limit))
    return 200


def get_job_stream(
    handler,
    query_single: Callable[[dict[str, list[str]], str], str | None],
    path: str,
    query: dict[str, list[str]],
) -> int:
    job_id = path.removeprefix("/jobs/").removesuffix("/stream").strip("/")
    if not job_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    timeout_seconds = float(query_single(query, "timeout") or 30.0)
    interval_seconds = float(query_single(query, "interval") or 0.25)
    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
    interval_seconds = min(5.0, max(0.05, interval_seconds))
    handler._stream_job_events(
        job_id=job_id,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    return 200


def get_job_item(handler, job_manager: JobManager, path: str) -> int:
    job_id = path.removeprefix("/jobs/").strip()
    if not job_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    item = job_manager.get(job_id)
    if item is None:
        handler._send_json(404, {"error": "Job not found"})
        return 404
    handler._send_json(200, item)
    return 200


def get_plans(
    handler,
    service: NovaAdaptService,
    query_single: Callable[[dict[str, list[str]], str], str | None],
    query: dict[str, list[str]],
) -> int:
    limit = int(query_single(query, "limit") or 50)
    handler._send_json(200, service.list_plans(limit=limit))
    return 200


def get_plan_stream(
    handler,
    query_single: Callable[[dict[str, list[str]], str], str | None],
    path: str,
    query: dict[str, list[str]],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/stream").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    timeout_seconds = float(query_single(query, "timeout") or 30.0)
    interval_seconds = float(query_single(query, "interval") or 0.25)
    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
    interval_seconds = min(5.0, max(0.05, interval_seconds))
    handler._stream_plan_events(
        plan_id=plan_id,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    return 200


def get_plan_item(handler, service: NovaAdaptService, path: str) -> int:
    plan_id = path.removeprefix("/plans/").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    item = service.get_plan(plan_id)
    if item is None:
        handler._send_json(404, {"error": "Plan not found"})
        return 404
    handler._send_json(200, item)
    return 200


def post_cancel_job(handler, path: str, payload: dict[str, object]) -> int:
    job_id = path.removeprefix("/jobs/").removesuffix("/cancel").strip("/")
    if not job_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: handler._cancel_job(job_id),
        category="jobs",
        action="cancel",
        entity_type="job",
        entity_id=job_id,
    )


def post_plan_approve(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/approve").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.approve_plan(plan_id, payload)),
        category="plans",
        action="approve",
        entity_type="plan",
        entity_id=plan_id,
    )


def post_plan_approve_async(
    handler,
    service: NovaAdaptService,
    job_manager: JobManager,
    path: str,
    payload: dict[str, object],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/approve_async").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (
            202,
            {
                "job_id": job_manager.submit(service.approve_plan, plan_id, payload),
                "status": "queued",
                "kind": "plan_approval",
            },
        ),
        category="plans",
        action="approve_async",
        entity_type="plan",
        entity_id=plan_id,
    )


def post_plan_retry_failed(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/retry_failed").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    retry_payload = dict(payload)
    retry_payload["execute"] = True
    retry_payload["retry_failed_only"] = True
    return handler._respond_idempotent(
        path=path,
        payload=retry_payload,
        operation=lambda: (200, service.approve_plan(plan_id, retry_payload)),
        category="plans",
        action="retry_failed",
        entity_type="plan",
        entity_id=plan_id,
    )


def post_plan_retry_failed_async(
    handler,
    service: NovaAdaptService,
    job_manager: JobManager,
    path: str,
    payload: dict[str, object],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/retry_failed_async").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    retry_payload = dict(payload)
    retry_payload["execute"] = True
    retry_payload["retry_failed_only"] = True
    return handler._respond_idempotent(
        path=path,
        payload=retry_payload,
        operation=lambda: (
            202,
            {
                "job_id": job_manager.submit(service.approve_plan, plan_id, retry_payload),
                "status": "queued",
                "kind": "plan_retry_failed",
            },
        ),
        category="plans",
        action="retry_failed_async",
        entity_type="plan",
        entity_id=plan_id,
    )


def post_plan_reject(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/reject").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    reason = payload.get("reason")
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.reject_plan(plan_id, reason=reason)),
        category="plans",
        action="reject",
        entity_type="plan",
        entity_id=plan_id,
    )


def post_plan_undo(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    plan_id = path.removeprefix("/plans/").removesuffix("/undo").strip("/")
    if not plan_id:
        handler._send_json(404, {"error": "Not found"})
        return 404
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.undo_plan(plan_id, payload)),
        category="plans",
        action="undo",
        entity_type="plan",
        entity_id=plan_id,
    )
