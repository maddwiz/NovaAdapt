from __future__ import annotations

import ipaddress
import json
import logging
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse

from .audit_store import AuditStore
from .dashboard import render_dashboard_html
from .idempotency_store import IdempotencyStore
from .job_store import JobStore
from .jobs import JobManager
from .openapi import build_openapi_spec
from .service import NovaAdaptService


DEFAULT_MAX_REQUEST_BODY_BYTES = 1 << 20  # 1 MiB
SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "api_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "session_token",
}


class PayloadTooLargeError(ValueError):
    pass


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class _PerClientSlidingWindowRateLimiter:
    """Simple thread-safe fixed-window limiter keyed by client identity."""

    def __init__(
        self,
        burst: int,
        window_seconds: float = 1.0,
        idle_ttl_seconds: float = 15 * 60,
    ) -> None:
        self.burst = max(1, burst)
        self.window_seconds = window_seconds
        self.idle_ttl_seconds = max(60.0, float(idle_ttl_seconds))
        self._timestamps: dict[str, deque[float]] = {}
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        normalized_key = str(key or "unknown").strip() or "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds
        idle_cutoff = now - self.idle_ttl_seconds
        with self._lock:
            stale_keys = [item for item, last in self._last_seen.items() if last < idle_cutoff]
            for item in stale_keys:
                self._last_seen.pop(item, None)
                self._timestamps.pop(item, None)

            timestamps = self._timestamps.setdefault(normalized_key, deque())
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            self._last_seen[normalized_key] = now
            if len(timestamps) >= self.burst:
                return False
            timestamps.append(now)
            return True


class _RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests_total = 0
        self.unauthorized_total = 0
        self.rate_limited_total = 0
        self.bad_request_total = 0
        self.server_errors_total = 0

    def inc(self, field: str) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def render(self) -> str:
        with self._lock:
            return (
                f"novaadapt_core_requests_total {self.requests_total}\n"
                f"novaadapt_core_unauthorized_total {self.unauthorized_total}\n"
                f"novaadapt_core_rate_limited_total {self.rate_limited_total}\n"
                f"novaadapt_core_bad_request_total {self.bad_request_total}\n"
                f"novaadapt_core_server_errors_total {self.server_errors_total}\n"
            )

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "novaadapt_core_requests_total": self.requests_total,
                "novaadapt_core_unauthorized_total": self.unauthorized_total,
                "novaadapt_core_rate_limited_total": self.rate_limited_total,
                "novaadapt_core_bad_request_total": self.bad_request_total,
                "novaadapt_core_server_errors_total": self.server_errors_total,
            }


class NovaAdaptHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls, job_manager: JobManager):
        super().__init__(server_address, handler_cls)
        self.job_manager = job_manager

    def server_close(self) -> None:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            manager.shutdown(wait=True)
        super().server_close()


def create_server(
    host: str,
    port: int,
    service: NovaAdaptService,
    api_token: str | None = None,
    job_manager: JobManager | None = None,
    log_requests: bool = False,
    logger: logging.Logger | None = None,
    rate_limit_rps: float = 0.0,
    rate_limit_burst: int | None = None,
    trusted_proxy_cidrs: list[str] | None = None,
    idempotency_retention_seconds: int = 7 * 24 * 60 * 60,
    idempotency_cleanup_interval_seconds: float = 60.0,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    jobs_db_path: str | None = None,
    idempotency_db_path: str | None = None,
    audit_db_path: str | None = None,
) -> ThreadingHTTPServer:
    managed_jobs = job_manager or JobManager(store=JobStore(jobs_db_path) if jobs_db_path else None)
    idempotency_store = (
        IdempotencyStore(
            idempotency_db_path,
            retention_seconds=idempotency_retention_seconds,
            cleanup_interval_seconds=idempotency_cleanup_interval_seconds,
        )
        if idempotency_db_path
        else None
    )
    audit_store = AuditStore(audit_db_path)
    metrics = _RequestMetrics()

    limiter = None
    if rate_limit_rps > 0:
        burst = rate_limit_burst if rate_limit_burst is not None else max(1, int(rate_limit_rps))
        limiter = _PerClientSlidingWindowRateLimiter(burst=burst, window_seconds=1.0)
    trusted_proxy_networks = _parse_trusted_proxy_cidrs(trusted_proxy_cidrs or [])

    handler_cls = _build_handler(
        service=service,
        api_token=api_token,
        job_manager=managed_jobs,
        log_requests=log_requests,
        logger=logger or logging.getLogger("novaadapt.api"),
        limiter=limiter,
        trusted_proxy_networks=trusted_proxy_networks,
        idempotency_store=idempotency_store,
        audit_store=audit_store,
        metrics=metrics,
        max_request_body_bytes=max(1, int(max_request_body_bytes)),
    )
    return NovaAdaptHTTPServer((host, port), handler_cls, managed_jobs)


def run_server(
    host: str,
    port: int,
    service: NovaAdaptService,
    api_token: str | None = None,
    log_requests: bool = False,
    logger: logging.Logger | None = None,
    rate_limit_rps: float = 0.0,
    rate_limit_burst: int | None = None,
    trusted_proxy_cidrs: list[str] | None = None,
    idempotency_retention_seconds: int = 7 * 24 * 60 * 60,
    idempotency_cleanup_interval_seconds: float = 60.0,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    jobs_db_path: str | None = None,
    idempotency_db_path: str | None = None,
    audit_db_path: str | None = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        service=service,
        api_token=api_token,
        log_requests=log_requests,
        logger=logger,
        rate_limit_rps=rate_limit_rps,
        rate_limit_burst=rate_limit_burst,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
        idempotency_retention_seconds=idempotency_retention_seconds,
        idempotency_cleanup_interval_seconds=idempotency_cleanup_interval_seconds,
        max_request_body_bytes=max_request_body_bytes,
        jobs_db_path=jobs_db_path,
        idempotency_db_path=idempotency_db_path,
        audit_db_path=audit_db_path,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler(
    service: NovaAdaptService,
    api_token: str | None,
    job_manager: JobManager,
    log_requests: bool,
    logger: logging.Logger,
    limiter: _PerClientSlidingWindowRateLimiter | None,
    trusted_proxy_networks: list[IPNetwork],
    idempotency_store: IdempotencyStore | None,
    audit_store: AuditStore | None,
    metrics: _RequestMetrics,
    max_request_body_bytes: int,
):
    class Handler(BaseHTTPRequestHandler):
        _request_id: str

        def do_GET(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            metrics.inc("requests_total")
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            try:
                if path == "/health":
                    deep = (_single(query, "deep") or "0") == "1"
                    if not deep:
                        status_code = 200
                        self._send_json(status_code, {"ok": True, "service": "novaadapt"})
                        return
                    health_payload = {"ok": True, "service": "novaadapt", "checks": {}, "metrics": metrics.snapshot()}
                    checks = health_payload["checks"]

                    config = _to_path(_single(query, "config"))
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

                    status_code = 200 if health_payload["ok"] else 503
                    self._send_json(status_code, health_payload)
                    return

                if path == "/dashboard":
                    if not self._check_auth(path, query):
                        status_code = 401
                        return
                    status_code = 200
                    self._send_html(status_code, render_dashboard_html())
                    return

                if path == "/dashboard/data":
                    if not self._check_auth(path, query):
                        status_code = 401
                        return
                    jobs_limit = int(_single(query, "jobs_limit") or 25)
                    plans_limit = int(_single(query, "plans_limit") or 25)
                    events_limit = int(_single(query, "events_limit") or 25)
                    config = _single(query, "config")
                    status_code = 200
                    self._send_json(
                        status_code,
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
                            "models_count": len(service.models(config_path=_to_path(config))),
                        },
                    )
                    return

                if path == "/openapi.json":
                    status_code = 200
                    self._send_json(status_code, build_openapi_spec())
                    return

                if path == "/metrics":
                    if not self._check_auth(path, query):
                        status_code = 401
                        return
                    status_code = 200
                    self._send_metrics(status_code)
                    return

                if path == "/events":
                    if not self._check_auth(path, query):
                        status_code = 401
                        return
                    limit = int(_single(query, "limit") or 100)
                    category = _single(query, "category")
                    entity_type = _single(query, "entity_type")
                    entity_id = _single(query, "entity_id")
                    since_id = _single(query, "since_id")
                    status_code = 200
                    self._send_json(
                        status_code,
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
                    return

                if path == "/events/stream":
                    if not self._check_auth(path, query):
                        status_code = 401
                        return
                    timeout_seconds = float(_single(query, "timeout") or 30.0)
                    interval_seconds = float(_single(query, "interval") or 0.25)
                    since_id = int(_single(query, "since_id") or 0)
                    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
                    interval_seconds = min(5.0, max(0.05, interval_seconds))
                    status_code = 200
                    self._stream_audit_events(
                        timeout_seconds=timeout_seconds,
                        interval_seconds=interval_seconds,
                        since_id=since_id,
                    )
                    return

                if self._is_rate_limited(path):
                    status_code = 429
                    metrics.inc("rate_limited_total")
                    self._send_json(status_code, {"error": "Rate limit exceeded"})
                    return

                if not self._check_auth(path, query):
                    status_code = 401
                    return

                if path == "/models":
                    config = _single(query, "config")
                    out = service.models(config_path=_to_path(config))
                    status_code = 200
                    self._send_json(status_code, out)
                    return

                if path == "/history":
                    limit = int(_single(query, "limit") or 20)
                    status_code = 200
                    self._send_json(status_code, service.history(limit=limit))
                    return

                if path == "/jobs":
                    limit = int(_single(query, "limit") or 50)
                    status_code = 200
                    self._send_json(status_code, job_manager.list(limit=limit))
                    return

                if path.startswith("/jobs/") and path.endswith("/stream"):
                    job_id = path.removeprefix("/jobs/").removesuffix("/stream").strip("/")
                    if not job_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    timeout_seconds = float(_single(query, "timeout") or 30.0)
                    interval_seconds = float(_single(query, "interval") or 0.25)
                    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
                    interval_seconds = min(5.0, max(0.05, interval_seconds))
                    status_code = 200
                    self._stream_job_events(
                        job_id=job_id,
                        timeout_seconds=timeout_seconds,
                        interval_seconds=interval_seconds,
                    )
                    return

                if path.startswith("/jobs/"):
                    job_id = path.removeprefix("/jobs/").strip()
                    if not job_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    item = job_manager.get(job_id)
                    if item is None:
                        status_code = 404
                        self._send_json(status_code, {"error": "Job not found"})
                        return
                    status_code = 200
                    self._send_json(status_code, item)
                    return

                if path == "/plans":
                    limit = int(_single(query, "limit") or 50)
                    status_code = 200
                    self._send_json(status_code, service.list_plans(limit=limit))
                    return

                if path.startswith("/plans/") and path.endswith("/stream"):
                    plan_id = path.removeprefix("/plans/").removesuffix("/stream").strip("/")
                    if not plan_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    timeout_seconds = float(_single(query, "timeout") or 30.0)
                    interval_seconds = float(_single(query, "interval") or 0.25)
                    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
                    interval_seconds = min(5.0, max(0.05, interval_seconds))
                    status_code = 200
                    self._stream_plan_events(
                        plan_id=plan_id,
                        timeout_seconds=timeout_seconds,
                        interval_seconds=interval_seconds,
                    )
                    return

                if path.startswith("/plans/"):
                    plan_id = path.removeprefix("/plans/").strip("/")
                    if not plan_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    item = service.get_plan(plan_id)
                    if item is None:
                        status_code = 404
                        self._send_json(status_code, {"error": "Plan not found"})
                        return
                    status_code = 200
                    self._send_json(status_code, item)
                    return

                status_code = 404
                self._send_json(status_code, {"error": "Not found"})
            except ValueError as exc:
                status_code = 400
                metrics.inc("bad_request_total")
                self._send_json(status_code, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                status_code = 500
                metrics.inc("server_errors_total")
                self._send_json(status_code, {"error": str(exc)})
            finally:
                self._log_request(status_code, started)

        def do_POST(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            metrics.inc("requests_total")
            parsed = urlparse(self.path)
            path = parsed.path

            if self._is_rate_limited(path):
                status_code = 429
                metrics.inc("rate_limited_total")
                self._send_json(status_code, {"error": "Rate limit exceeded"})
                self._log_request(status_code, started)
                return

            if not self._check_auth(path):
                status_code = 401
                self._log_request(status_code, started)
                return

            try:
                payload = self._read_json_body()

                if path.startswith("/jobs/") and path.endswith("/cancel"):
                    job_id = path.removeprefix("/jobs/").removesuffix("/cancel").strip("/")
                    if not job_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: self._cancel_job(job_id),
                    )
                    self._audit_event(
                        category="jobs",
                        action="cancel",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="job",
                        entity_id=job_id,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path == "/plans":
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (201, service.create_plan(payload)),
                    )
                    self._audit_event(
                        category="plans",
                        action="create",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="plan",
                        entity_id=str(response_payload.get("id")) if isinstance(response_payload, dict) else None,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path.startswith("/plans/") and path.endswith("/approve"):
                    plan_id = path.removeprefix("/plans/").removesuffix("/approve").strip("/")
                    if not plan_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (200, service.approve_plan(plan_id, payload)),
                    )
                    self._audit_event(
                        category="plans",
                        action="approve",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="plan",
                        entity_id=plan_id,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path.startswith("/plans/") and path.endswith("/approve_async"):
                    plan_id = path.removeprefix("/plans/").removesuffix("/approve_async").strip("/")
                    if not plan_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (
                            202,
                            {
                                "job_id": job_manager.submit(service.approve_plan, plan_id, payload),
                                "status": "queued",
                                "kind": "plan_approval",
                            },
                        ),
                    )
                    self._audit_event(
                        category="plans",
                        action="approve_async",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="plan",
                        entity_id=plan_id,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path.startswith("/plans/") and path.endswith("/reject"):
                    plan_id = path.removeprefix("/plans/").removesuffix("/reject").strip("/")
                    if not plan_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    reason = payload.get("reason")
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (
                            200,
                            service.reject_plan(plan_id, reason=str(reason) if reason is not None else None),
                        ),
                    )
                    self._audit_event(
                        category="plans",
                        action="reject",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="plan",
                        entity_id=plan_id,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path.startswith("/plans/") and path.endswith("/undo"):
                    plan_id = path.removeprefix("/plans/").removesuffix("/undo").strip("/")
                    if not plan_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (200, service.undo_plan(plan_id, payload)),
                    )
                    self._audit_event(
                        category="plans",
                        action="undo",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="plan",
                        entity_id=plan_id,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path == "/run":
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (200, service.run(payload)),
                    )
                    self._audit_event(
                        category="run",
                        action="run",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path == "/run_async":
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (
                            202,
                            {"job_id": job_manager.submit(service.run, payload), "status": "queued"},
                        ),
                    )
                    self._audit_event(
                        category="run",
                        action="run_async",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        entity_type="job",
                        entity_id=str(response_payload.get("job_id")) if isinstance(response_payload, dict) else None,
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path == "/undo":
                    status_code, response_payload, replayed = self._execute_idempotent(
                        path,
                        payload,
                        lambda: (200, service.undo(payload)),
                    )
                    self._audit_event(
                        category="undo",
                        action="undo",
                        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                        payload=response_payload if isinstance(response_payload, dict) else None,
                    )
                    self._send_json(
                        status_code,
                        response_payload,
                        replayed=replayed,
                        idempotency_key=self._idempotency_key(),
                    )
                    return

                if path == "/check":
                    config = _to_path(payload.get("config"))
                    models = payload.get("models")
                    probe = str(payload.get("probe", "Reply with: OK"))
                    out = service.check(config_path=config, model_names=service._as_name_list(models), probe_prompt=probe)
                    status_code = 200
                    self._send_json(status_code, out)
                    return

                status_code = 404
                self._send_json(status_code, {"error": "Not found"})
            except PayloadTooLargeError as exc:
                status_code = 413
                metrics.inc("bad_request_total")
                self._send_json(status_code, {"error": str(exc)})
            except ValueError as exc:
                status_code = 400
                metrics.inc("bad_request_total")
                self._send_json(status_code, {"error": str(exc)})
            except json.JSONDecodeError:
                status_code = 400
                metrics.inc("bad_request_total")
                self._send_json(status_code, {"error": "Request body must be valid JSON"})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                status_code = 500
                metrics.inc("server_errors_total")
                self._send_json(status_code, {"error": str(exc)})
            finally:
                self._log_request(status_code, started)

        def _is_rate_limited(self, path: str) -> bool:
            if limiter is None:
                return False
            if path in {"/health", "/metrics"}:
                return False
            return not limiter.allow(self._rate_limit_client_key())

        def _rate_limit_client_key(self) -> str:
            remote_ip = _parse_ip_token(self.client_address[0] if self.client_address else "")
            if remote_ip is not None and _ip_in_networks(remote_ip, trusted_proxy_networks):
                forwarded = _first_forwarded_ip(self.headers.get("X-Forwarded-For", ""))
                if forwarded is not None:
                    return str(forwarded)
            if remote_ip is not None:
                return str(remote_ip)
            remote_host = self.client_address[0] if self.client_address else ""
            remote_host = str(remote_host or "").strip()
            return remote_host or "unknown"

        def _check_auth(self, path: str, query: dict[str, list[str]] | None = None) -> bool:
            if path == "/health" or not api_token:
                return True
            if query is not None and path in {"/dashboard", "/dashboard/data"}:
                query_token = _single(query, "token")
                if query_token == api_token:
                    return True
            auth_header = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            if auth_header == expected:
                return True
            metrics.inc("unauthorized_total")
            self._send_json(401, {"error": "Unauthorized"}, unauthorized=True)
            return False

        def _read_json_body(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > max_request_body_bytes:
                raise PayloadTooLargeError("Request body too large")
            if content_length <= 0:
                return {}

            raw = self.rfile.read(min(content_length, max_request_body_bytes + 1)).decode("utf-8")
            if len(raw.encode("utf-8")) > max_request_body_bytes:
                raise PayloadTooLargeError("Request body too large")
            if not raw.strip():
                return {}
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
            raise ValueError("Request JSON body must be an object")

        def _send_json(
            self,
            status_code: int,
            payload: object,
            unauthorized: bool = False,
            replayed: bool = False,
            idempotency_key: str | None = None,
        ) -> None:
            if isinstance(payload, dict):
                payload = dict(payload)
                payload.setdefault("request_id", self._request_id)
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", self._request_id)
            if replayed:
                self.send_header("X-Idempotency-Replayed", "true")
            if idempotency_key:
                self.send_header("Idempotency-Key", idempotency_key)
            if unauthorized:
                self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_metrics(self, status_code: int) -> None:
            encoded = metrics.render().encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("X-Request-ID", self._request_id)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_html(self, status_code: int, html: str) -> None:
            encoded = html.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Request-ID", self._request_id)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _cancel_job(self, job_id: str) -> tuple[int, object]:
            canceled = job_manager.cancel(job_id)
            if canceled is None:
                return 404, {"error": "Job not found"}
            return 200, canceled

        def _idempotency_key(self) -> str | None:
            value = self.headers.get("Idempotency-Key", "").strip()
            if value:
                return value
            return None

        @staticmethod
        def _is_idempotent_route(path: str) -> bool:
            if path in {"/run", "/run_async", "/undo", "/plans"}:
                return True
            if path.startswith("/jobs/") and path.endswith("/cancel"):
                return True
            if path.startswith("/plans/") and (
                path.endswith("/approve")
                or path.endswith("/approve_async")
                or path.endswith("/reject")
                or path.endswith("/undo")
            ):
                return True
            return False

        def _execute_idempotent(
            self,
            path: str,
            payload: dict[str, object],
            operation,
        ) -> tuple[int, object, bool]:
            key = self._idempotency_key()
            if idempotency_store is None or key is None or not self._is_idempotent_route(path):
                status_code, response_payload = operation()
                return int(status_code), response_payload, False

            state, record = idempotency_store.begin(
                key=key,
                method="POST",
                path=path,
                payload=payload,
            )
            if state == "replay":
                replay_status = int(record["status_code"]) if record else 200
                replay_payload = record["payload"] if record else {}
                return replay_status, replay_payload, True
            if state in {"conflict", "in_progress"}:
                return 409, {"error": record["error"] if record else "Idempotency conflict"}, False

            try:
                status_code, response_payload = operation()
            except Exception:
                idempotency_store.clear(key=key, method="POST", path=path)
                raise

            idempotency_store.complete(
                key=key,
                method="POST",
                path=path,
                status_code=int(status_code),
                payload=response_payload,
            )
            return int(status_code), response_payload, False

        def _stream_job_events(self, job_id: str, timeout_seconds: float, interval_seconds: float) -> None:
            current = job_manager.get(job_id)
            if current is None:
                self._send_json(404, {"error": "Job not found"})
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Request-ID", self._request_id)
            self.end_headers()

            last_snapshot: str | None = None
            deadline = time.monotonic() + timeout_seconds
            while True:
                current = job_manager.get(job_id)
                if current is None:
                    self._write_sse_event("error", {"error": "Job not found", "id": job_id})
                    return

                snapshot = json.dumps(current, sort_keys=True, separators=(",", ":"))
                if snapshot != last_snapshot:
                    payload = dict(current)
                    payload.setdefault("request_id", self._request_id)
                    if not self._write_sse_event("job", payload):
                        return
                    last_snapshot = snapshot

                status = str(current.get("status", ""))
                if status in {"succeeded", "failed", "canceled"}:
                    self._write_sse_event(
                        "end",
                        {"id": job_id, "status": status, "request_id": self._request_id},
                    )
                    return

                if time.monotonic() >= deadline:
                    self._write_sse_event("timeout", {"id": job_id, "request_id": self._request_id})
                    return

                time.sleep(interval_seconds)

        def _stream_plan_events(self, plan_id: str, timeout_seconds: float, interval_seconds: float) -> None:
            current = service.get_plan(plan_id)
            if current is None:
                self._send_json(404, {"error": "Plan not found"})
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Request-ID", self._request_id)
            self.end_headers()

            last_snapshot: str | None = None
            deadline = time.monotonic() + timeout_seconds
            while True:
                current = service.get_plan(plan_id)
                if current is None:
                    self._write_sse_event("error", {"error": "Plan not found", "id": plan_id})
                    return

                snapshot = json.dumps(current, sort_keys=True, separators=(",", ":"))
                if snapshot != last_snapshot:
                    payload = dict(current)
                    payload.setdefault("request_id", self._request_id)
                    if not self._write_sse_event("plan", payload):
                        return
                    last_snapshot = snapshot

                status = str(current.get("status", ""))
                if status in {"approved", "rejected", "executed", "failed"}:
                    self._write_sse_event(
                        "end",
                        {"id": plan_id, "status": status, "request_id": self._request_id},
                    )
                    return

                if time.monotonic() >= deadline:
                    self._write_sse_event("timeout", {"id": plan_id, "request_id": self._request_id})
                    return

                time.sleep(interval_seconds)

        def _stream_audit_events(self, timeout_seconds: float, interval_seconds: float, since_id: int) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Request-ID", self._request_id)
            self.end_headers()

            last_id = max(0, int(since_id))
            deadline = time.monotonic() + timeout_seconds
            while True:
                rows = (
                    audit_store.list(limit=200, since_id=last_id)
                    if audit_store is not None
                    else []
                )
                if rows:
                    # list() is descending; stream oldest-to-newest for natural ordering
                    for item in reversed(rows):
                        payload = dict(item)
                        payload.setdefault("request_id", self._request_id)
                        if not self._write_sse_event("audit", payload):
                            return
                        last_id = max(last_id, int(item.get("id", 0)))

                if time.monotonic() >= deadline:
                    self._write_sse_event("timeout", {"request_id": self._request_id})
                    return

                time.sleep(interval_seconds)

        def _audit_event(
            self,
            *,
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
                    request_id=self._request_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    payload=payload,
                )
            except Exception as exc:  # pragma: no cover - audit should never fail request path
                logger.warning("audit append failed request_id=%s error=%s", self._request_id, exc)

        def _write_sse_event(self, event: str, payload: dict[str, object]) -> bool:
            encoded = (
                f"event: {event}\n"
                f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"
            ).encode("utf-8")
            try:
                self.wfile.write(encoded)
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError):
                return False

        def _log_request(self, status_code: int, started: float) -> None:
            if not log_requests:
                return
            duration_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "core request id=%s method=%s path=%s status=%s duration_ms=%.2f",
                self._request_id,
                self.command,
                _redact_path_for_logs(self.path),
                status_code,
                duration_ms,
            )

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def _single(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _to_path(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        from pathlib import Path

        return Path(value)
    return None


def _normalize_request_id(value: str | None) -> str:
    if value and value.strip():
        return value.strip()
    return secrets.token_hex(12)


def _parse_trusted_proxy_cidrs(values: list[str]) -> list[IPNetwork]:
    networks: list[IPNetwork] = []
    for raw in values:
        item = str(raw).strip()
        if not item:
            continue
        try:
            if "/" in item:
                network = ipaddress.ip_network(item, strict=False)
            else:
                ip = ipaddress.ip_address(item)
                suffix = 32 if isinstance(ip, ipaddress.IPv4Address) else 128
                network = ipaddress.ip_network(f"{ip}/{suffix}", strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid trusted proxy CIDR/IP: {item}") from exc
        networks.append(network)
    return networks


def _ip_in_networks(ip: IPAddress, networks: list[IPNetwork]) -> bool:
    return any(ip in network for network in networks)


def _first_forwarded_ip(value: str) -> IPAddress | None:
    for token in str(value).split(","):
        parsed = _parse_ip_token(token)
        if parsed is not None:
            return parsed
    return None


def _parse_ip_token(value: str) -> IPAddress | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.startswith("[") and "]" in token:
        token = token[1 : token.find("]")]
    elif token.count(":") == 1 and "." in token:
        host, port = token.rsplit(":", 1)
        if port.isdigit():
            token = host
    try:
        return ipaddress.ip_address(token)
    except ValueError:
        return None


def _redact_path_for_logs(raw_path: str) -> str:
    parsed = urlparse(raw_path)
    if not parsed.query:
        return parsed.path or raw_path
    redacted_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            redacted_pairs.append((key, "redacted"))
        else:
            redacted_pairs.append((key, value))
    redacted_query = urlencode(redacted_pairs, doseq=True)
    if not redacted_query:
        return parsed.path or raw_path
    return f"{parsed.path}?{redacted_query}"
