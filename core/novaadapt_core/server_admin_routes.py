from __future__ import annotations

from .audit_store import AuditStore
from .dashboard import render_dashboard_html
from .openapi import build_openapi_spec
from .service import NovaAdaptService


def get_health(
    handler,
    service: NovaAdaptService,
    audit_store: AuditStore | None,
    metrics,
    single,
    to_path,
    query: dict[str, list[str]],
) -> int:
    deep = (single(query, "deep") or "0") == "1"
    if not deep:
        handler._send_json(200, {"ok": True, "service": "novaadapt"})
        return 200

    include_execution_check = (single(query, "execution") or "0") == "1"
    health_payload = {"ok": True, "service": "novaadapt", "checks": {}, "metrics": metrics.snapshot()}
    checks = health_payload["checks"]

    config = to_path(single(query, "config"))
    try:
        checks["models"] = {"ok": True, "count": len(service.models(config_path=config))}
    except Exception as exc:
        checks["models"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["audit_store"] = {
            "ok": True,
            "recent_count": len(audit_store.list(limit=1)) if audit_store is not None else 0,
        }
    except Exception as exc:
        checks["audit_store"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["plan_store"] = {"ok": True, "recent_count": len(service.list_plans(limit=1))}
    except Exception as exc:
        checks["plan_store"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["action_log"] = {"ok": True, "recent_count": len(service.history(limit=1))}
    except Exception as exc:
        checks["action_log"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["memory"] = service.memory_status()
        if not bool(checks["memory"].get("ok", False)) and bool(checks["memory"].get("enabled", True)):
            health_payload["ok"] = False
    except Exception as exc:
        checks["memory"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    if include_execution_check:
        try:
            checks["directshell"] = service.directshell_probe()
            if not bool(checks["directshell"].get("ok")):
                health_payload["ok"] = False
        except Exception as exc:
            checks["directshell"] = {"ok": False, "error": str(exc)}
            health_payload["ok"] = False

    status_code = 200 if health_payload["ok"] else 503
    handler._send_json(status_code, health_payload)
    return status_code


def get_dashboard(handler, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/dashboard", query):
        return 401
    handler._send_html(200, render_dashboard_html())
    return 200


def get_dashboard_data(
    handler,
    service: NovaAdaptService,
    job_manager,
    audit_store: AuditStore | None,
    metrics,
    single,
    to_path,
    query: dict[str, list[str]],
) -> int:
    if not handler._check_auth("/dashboard/data", query):
        return 401
    jobs_limit = int(single(query, "jobs_limit") or 25)
    plans_limit = int(single(query, "plans_limit") or 25)
    events_limit = int(single(query, "events_limit") or 25)
    config = single(query, "config")
    handler._send_json(
        200,
        {
            "health": {"ok": True, "service": "novaadapt"},
            "metrics": metrics.snapshot(),
            "jobs": job_manager.list(limit=max(1, jobs_limit)),
            "plans": service.list_plans(limit=max(1, plans_limit)),
            "events": (
                audit_store.list(limit=max(1, events_limit))
                if audit_store is not None
                else []
            ),
            "models_count": len(service.models(config_path=to_path(config))),
        },
    )
    return 200


def get_openapi(handler) -> int:
    handler._send_json(200, build_openapi_spec())
    return 200


def get_metrics(handler, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/metrics", query):
        return 401
    handler._send_metrics(200)
    return 200


def get_events(handler, audit_store: AuditStore | None, single, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/events", query):
        return 401
    limit = int(single(query, "limit") or 100)
    category = single(query, "category")
    entity_type = single(query, "entity_type")
    entity_id = single(query, "entity_id")
    since_id = single(query, "since_id")
    handler._send_json(
        200,
        audit_store.list(
            limit=max(1, limit),
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            since_id=int(since_id) if since_id is not None else None,
        )
        if audit_store is not None
        else [],
    )
    return 200


def get_events_stream(handler, single, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/events/stream", query):
        return 401
    timeout_seconds = float(single(query, "timeout") or 30.0)
    interval_seconds = float(single(query, "interval") or 0.25)
    since_id = int(single(query, "since_id") or 0)
    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
    interval_seconds = min(5.0, max(0.05, interval_seconds))
    handler._stream_audit_events(
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        since_id=since_id,
    )
    return 200
