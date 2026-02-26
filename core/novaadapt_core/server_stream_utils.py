from __future__ import annotations

import json
import time
import logging

from .audit_store import AuditStore
from .jobs import JobManager
from .service import NovaAdaptService


def write_sse_event(handler, event: str, payload: dict[str, object]) -> bool:
    encoded = (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"
    ).encode("utf-8")
    try:
        handler.wfile.write(encoded)
        handler.wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError):
        return False


def stream_job_events(
    handler,
    job_manager: JobManager,
    job_id: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> None:
    current = job_manager.get(job_id)
    if current is None:
        handler._send_json(404, {"error": "Job not found"})
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.send_header("X-Request-ID", handler._request_id)
    handler.end_headers()

    last_snapshot: str | None = None
    deadline = time.monotonic() + timeout_seconds
    while True:
        current = job_manager.get(job_id)
        if current is None:
            write_sse_event(handler, "error", {"error": "Job not found", "id": job_id})
            return

        snapshot = json.dumps(current, sort_keys=True, separators=(",", ":"))
        if snapshot != last_snapshot:
            payload = dict(current)
            payload.setdefault("request_id", handler._request_id)
            if not write_sse_event(handler, "job", payload):
                return
            last_snapshot = snapshot

        status = str(current.get("status", ""))
        if status in {"succeeded", "failed", "canceled"}:
            write_sse_event(
                handler,
                "end",
                {"id": job_id, "status": status, "request_id": handler._request_id},
            )
            return

        if time.monotonic() >= deadline:
            write_sse_event(handler, "timeout", {"id": job_id, "request_id": handler._request_id})
            return

        time.sleep(interval_seconds)


def stream_plan_events(
    handler,
    service: NovaAdaptService,
    plan_id: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> None:
    current = service.get_plan(plan_id)
    if current is None:
        handler._send_json(404, {"error": "Plan not found"})
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.send_header("X-Request-ID", handler._request_id)
    handler.end_headers()

    last_snapshot: str | None = None
    deadline = time.monotonic() + timeout_seconds
    while True:
        current = service.get_plan(plan_id)
        if current is None:
            write_sse_event(handler, "error", {"error": "Plan not found", "id": plan_id})
            return

        snapshot = json.dumps(current, sort_keys=True, separators=(",", ":"))
        if snapshot != last_snapshot:
            payload = dict(current)
            payload.setdefault("request_id", handler._request_id)
            if not write_sse_event(handler, "plan", payload):
                return
            last_snapshot = snapshot

        status = str(current.get("status", ""))
        if status in {"approved", "rejected", "executed", "failed"}:
            write_sse_event(
                handler,
                "end",
                {"id": plan_id, "status": status, "request_id": handler._request_id},
            )
            return

        if time.monotonic() >= deadline:
            write_sse_event(handler, "timeout", {"id": plan_id, "request_id": handler._request_id})
            return

        time.sleep(interval_seconds)


def stream_audit_events(
    handler,
    audit_store: AuditStore | None,
    timeout_seconds: float,
    interval_seconds: float,
    since_id: int,
) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.send_header("X-Request-ID", handler._request_id)
    handler.end_headers()

    last_id = max(0, int(since_id))
    deadline = time.monotonic() + timeout_seconds
    while True:
        rows = audit_store.list(limit=200, since_id=last_id) if audit_store is not None else []
        if rows:
            # list() is descending; stream oldest-to-newest for natural ordering
            for item in reversed(rows):
                payload = dict(item)
                payload.setdefault("request_id", handler._request_id)
                if not write_sse_event(handler, "audit", payload):
                    return
                last_id = max(last_id, int(item.get("id", 0)))

        if time.monotonic() >= deadline:
            write_sse_event(handler, "timeout", {"request_id": handler._request_id})
            return

        time.sleep(interval_seconds)


def audit_event(
    *,
    audit_store: AuditStore | None,
    logger: logging.Logger,
    request_id: str,
    category: str,
    action: str,
    status: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    if audit_store is None:
        return
    try:
        audit_store.append(
            category=category,
            action=action,
            status=status,
            request_id=request_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
    except Exception as exc:  # pragma: no cover - audit should never fail request path
        logger.warning("audit append failed request_id=%s error=%s", request_id, exc)
