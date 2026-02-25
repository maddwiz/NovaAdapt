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
from .observability import configure_tracing, start_span
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
    audit_retention_seconds: int = 30 * 24 * 60 * 60,
    audit_cleanup_interval_seconds: float = 60.0,
    otel_enabled: bool = False,
    otel_service_name: str = "novaadapt-core",
    otel_exporter_endpoint: str | None = None,
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
    audit_store = AuditStore(
        audit_db_path,
        retention_seconds=audit_retention_seconds,
        cleanup_interval_seconds=audit_cleanup_interval_seconds,
    )
    metrics = _RequestMetrics()
    configure_tracing(
        enabled=otel_enabled,
        service_name=otel_service_name,
        exporter_endpoint=otel_exporter_endpoint,
    )

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
    audit_retention_seconds: int = 30 * 24 * 60 * 60,
    audit_cleanup_interval_seconds: float = 60.0,
    otel_enabled: bool = False,
    otel_service_name: str = "novaadapt-core",
    otel_exporter_endpoint: str | None = None,
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
        audit_retention_seconds=audit_retention_seconds,
        audit_cleanup_interval_seconds=audit_cleanup_interval_seconds,
        otel_enabled=otel_enabled,
        otel_service_name=otel_service_name,
        otel_exporter_endpoint=otel_exporter_endpoint,
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

            with start_span(
                "core.http.get",
                attributes={
                    "http.method": "GET",
                    "http.path": path,
                    "http.request_id": self._request_id,
                },
            ) as span:
                try:
                    status_code = self._dispatch_get(path, query)
                except ValueError as exc:
                    status_code = 400
                    metrics.inc("bad_request_total")
                    self._send_json(status_code, {"error": str(exc)})
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    status_code = 500
                    metrics.inc("server_errors_total")
                    self._send_json(status_code, {"error": str(exc)})
                finally:
                    if span is not None:
                        span.set_attribute("http.status_code", int(status_code))
                    self._log_request(status_code, started)

        def do_POST(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            metrics.inc("requests_total")
            parsed = urlparse(self.path)
            path = parsed.path

            with start_span(
                "core.http.post",
                attributes={
                    "http.method": "POST",
                    "http.path": path,
                    "http.request_id": self._request_id,
                },
            ) as span:
                try:
                    status_code = self._dispatch_post(path)
                except PayloadTooLargeError as exc:
                    status_code = 413
                    metrics.inc("bad_request_total")
                    self._send_json(status_code, {"error": str(exc)})
                except ValueError as exc:
                    status_code = 400
                    metrics.inc("bad_request_total")
                    self._send_json(status_code, {"error": str(exc)})
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    status_code = 500
                    metrics.inc("server_errors_total")
                    self._send_json(status_code, {"error": str(exc)})
                finally:
                    if span is not None:
                        span.set_attribute("http.status_code", int(status_code))
                    self._log_request(status_code, started)

        def _dispatch_get(self, path: str, query: dict[str, list[str]]) -> int:
            public_exact: dict[str, object] = {
                "/health": self._get_health,
                "/dashboard": self._get_dashboard,
                "/dashboard/data": self._get_dashboard_data,
                "/openapi.json": self._get_openapi,
                "/metrics": self._get_metrics,
                "/events": self._get_events,
                "/events/stream": self._get_events_stream,
            }
            handler = public_exact.get(path)
            if handler is not None:
                return int(handler(query))

            if self._is_rate_limited(path):
                metrics.inc("rate_limited_total")
                self._send_json(429, {"error": "Rate limit exceeded"})
                return 429

            if not self._check_auth(path, query):
                return 401

            private_exact: dict[str, object] = {
                "/models": self._get_models,
                "/history": self._get_history,
                "/jobs": self._get_jobs,
                "/plans": self._get_plans,
                "/plugins": self._get_plugins,
            }
            handler = private_exact.get(path)
            if handler is not None:
                return int(handler(query))

            dynamic_routes: tuple[tuple[str, str, object], ...] = (
                ("/jobs/", "/stream", self._get_job_stream),
                ("/jobs/", "", self._get_job_item),
                ("/plans/", "/stream", self._get_plan_stream),
                ("/plans/", "", self._get_plan_item),
                ("/plugins/", "/health", self._get_plugin_health),
            )
            for prefix, suffix, route_handler in dynamic_routes:
                if path.startswith(prefix) and (suffix == "" or path.endswith(suffix)):
                    return int(route_handler(path, query))

            self._send_json(404, {"error": "Not found"})
            return 404

        def _dispatch_post(self, path: str) -> int:
            if self._is_rate_limited(path):
                metrics.inc("rate_limited_total")
                self._send_json(429, {"error": "Rate limit exceeded"})
                return 429

            if not self._check_auth(path):
                return 401

            payload = self._read_json_body()

            exact_routes: dict[str, object] = {
                "/plans": lambda body: self._post_create_plan("/plans", body),
                "/run": lambda body: self._post_run("/run", body),
                "/run_async": lambda body: self._post_run_async("/run_async", body),
                "/undo": lambda body: self._post_undo("/undo", body),
                "/check": self._post_check,
                "/feedback": lambda body: self._post_feedback("/feedback", body),
            }
            handler = exact_routes.get(path)
            if handler is not None:
                return int(handler(payload))

            dynamic_routes: tuple[tuple[str, str, object], ...] = (
                ("/jobs/", "/cancel", self._post_cancel_job),
                ("/plugins/", "/call", self._post_plugin_call),
                ("/plans/", "/approve_async", self._post_plan_approve_async),
                ("/plans/", "/retry_failed_async", self._post_plan_retry_failed_async),
                ("/plans/", "/retry_failed", self._post_plan_retry_failed),
                ("/plans/", "/approve", self._post_plan_approve),
                ("/plans/", "/reject", self._post_plan_reject),
                ("/plans/", "/undo", self._post_plan_undo),
            )
            for prefix, suffix, route_handler in dynamic_routes:
                if path.startswith(prefix) and path.endswith(suffix):
                    return int(route_handler(path, payload))

            self._send_json(404, {"error": "Not found"})
            return 404

        def _get_health(self, query: dict[str, list[str]]) -> int:
            deep = (_single(query, "deep") or "0") == "1"
            if not deep:
                self._send_json(200, {"ok": True, "service": "novaadapt"})
                return 200
            include_execution_check = (_single(query, "execution") or "0") == "1"

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
            self._send_json(status_code, health_payload)
            return status_code

        def _get_dashboard(self, query: dict[str, list[str]]) -> int:
            if not self._check_auth("/dashboard", query):
                return 401
            self._send_html(200, render_dashboard_html())
            return 200

        def _get_dashboard_data(self, query: dict[str, list[str]]) -> int:
            if not self._check_auth("/dashboard/data", query):
                return 401
            jobs_limit = int(_single(query, "jobs_limit") or 25)
            plans_limit = int(_single(query, "plans_limit") or 25)
            events_limit = int(_single(query, "events_limit") or 25)
            config = _single(query, "config")
            self._send_json(
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
                    "models_count": len(service.models(config_path=_to_path(config))),
                },
            )
            return 200

        def _get_openapi(self, _query: dict[str, list[str]]) -> int:
            self._send_json(200, build_openapi_spec())
            return 200

        def _get_metrics(self, query: dict[str, list[str]]) -> int:
            if not self._check_auth("/metrics", query):
                return 401
            self._send_metrics(200)
            return 200

        def _get_events(self, query: dict[str, list[str]]) -> int:
            if not self._check_auth("/events", query):
                return 401
            limit = int(_single(query, "limit") or 100)
            category = _single(query, "category")
            entity_type = _single(query, "entity_type")
            entity_id = _single(query, "entity_id")
            since_id = _single(query, "since_id")
            self._send_json(
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

        def _get_events_stream(self, query: dict[str, list[str]]) -> int:
            if not self._check_auth("/events/stream", query):
                return 401
            timeout_seconds = float(_single(query, "timeout") or 30.0)
            interval_seconds = float(_single(query, "interval") or 0.25)
            since_id = int(_single(query, "since_id") or 0)
            timeout_seconds = min(300.0, max(1.0, timeout_seconds))
            interval_seconds = min(5.0, max(0.05, interval_seconds))
            self._stream_audit_events(
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
                since_id=since_id,
            )
            return 200

        def _get_models(self, query: dict[str, list[str]]) -> int:
            config = _single(query, "config")
            self._send_json(200, service.models(config_path=_to_path(config)))
            return 200

        def _get_history(self, query: dict[str, list[str]]) -> int:
            limit = int(_single(query, "limit") or 20)
            self._send_json(200, service.history(limit=limit))
            return 200

        def _get_jobs(self, query: dict[str, list[str]]) -> int:
            limit = int(_single(query, "limit") or 50)
            self._send_json(200, job_manager.list(limit=limit))
            return 200

        def _get_job_stream(self, path: str, query: dict[str, list[str]]) -> int:
            job_id = path.removeprefix("/jobs/").removesuffix("/stream").strip("/")
            if not job_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            timeout_seconds = float(_single(query, "timeout") or 30.0)
            interval_seconds = float(_single(query, "interval") or 0.25)
            timeout_seconds = min(300.0, max(1.0, timeout_seconds))
            interval_seconds = min(5.0, max(0.05, interval_seconds))
            self._stream_job_events(
                job_id=job_id,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
            )
            return 200

        def _get_job_item(self, path: str, _query: dict[str, list[str]]) -> int:
            job_id = path.removeprefix("/jobs/").strip()
            if not job_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            item = job_manager.get(job_id)
            if item is None:
                self._send_json(404, {"error": "Job not found"})
                return 404
            self._send_json(200, item)
            return 200

        def _get_plans(self, query: dict[str, list[str]]) -> int:
            limit = int(_single(query, "limit") or 50)
            self._send_json(200, service.list_plans(limit=limit))
            return 200

        def _get_plugins(self, _query: dict[str, list[str]]) -> int:
            self._send_json(200, service.plugins())
            return 200

        def _get_plugin_health(self, path: str, _query: dict[str, list[str]]) -> int:
            plugin_name = path.removeprefix("/plugins/").removesuffix("/health").strip("/")
            if not plugin_name:
                self._send_json(404, {"error": "Not found"})
                return 404
            self._send_json(200, service.plugin_health(plugin_name))
            return 200

        def _get_plan_stream(self, path: str, query: dict[str, list[str]]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/stream").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            timeout_seconds = float(_single(query, "timeout") or 30.0)
            interval_seconds = float(_single(query, "interval") or 0.25)
            timeout_seconds = min(300.0, max(1.0, timeout_seconds))
            interval_seconds = min(5.0, max(0.05, interval_seconds))
            self._stream_plan_events(
                plan_id=plan_id,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
            )
            return 200

        def _get_plan_item(self, path: str, _query: dict[str, list[str]]) -> int:
            plan_id = path.removeprefix("/plans/").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            item = service.get_plan(plan_id)
            if item is None:
                self._send_json(404, {"error": "Plan not found"})
                return 404
            self._send_json(200, item)
            return 200

        def _post_cancel_job(self, path: str, payload: dict[str, object]) -> int:
            job_id = path.removeprefix("/jobs/").removesuffix("/cancel").strip("/")
            if not job_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: self._cancel_job(job_id),
                category="jobs",
                action="cancel",
                entity_type="job",
                entity_id=job_id,
            )

        def _post_create_plan(self, path: str, payload: dict[str, object]) -> int:
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (201, service.create_plan(payload)),
                category="plans",
                action="create",
                entity_type="plan",
                entity_id_key="id",
            )

        def _post_plan_approve(self, path: str, payload: dict[str, object]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/approve").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.approve_plan(plan_id, payload)),
                category="plans",
                action="approve",
                entity_type="plan",
                entity_id=plan_id,
            )

        def _post_plan_approve_async(self, path: str, payload: dict[str, object]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/approve_async").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            return self._respond_idempotent(
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

        def _post_plan_retry_failed(self, path: str, payload: dict[str, object]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/retry_failed").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            retry_payload = dict(payload)
            retry_payload["execute"] = True
            retry_payload["retry_failed_only"] = True
            return self._respond_idempotent(
                path=path,
                payload=retry_payload,
                operation=lambda: (200, service.approve_plan(plan_id, retry_payload)),
                category="plans",
                action="retry_failed",
                entity_type="plan",
                entity_id=plan_id,
            )

        def _post_plan_retry_failed_async(self, path: str, payload: dict[str, object]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/retry_failed_async").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            retry_payload = dict(payload)
            retry_payload["execute"] = True
            retry_payload["retry_failed_only"] = True
            return self._respond_idempotent(
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

        def _post_plan_reject(self, path: str, payload: dict[str, object]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/reject").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            reason = payload.get("reason")
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.reject_plan(plan_id, reason=reason)),
                category="plans",
                action="reject",
                entity_type="plan",
                entity_id=plan_id,
            )

        def _post_plan_undo(self, path: str, payload: dict[str, object]) -> int:
            plan_id = path.removeprefix("/plans/").removesuffix("/undo").strip("/")
            if not plan_id:
                self._send_json(404, {"error": "Not found"})
                return 404
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.undo_plan(plan_id, payload)),
                category="plans",
                action="undo",
                entity_type="plan",
                entity_id=plan_id,
            )

        def _post_run(self, path: str, payload: dict[str, object]) -> int:
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.run(payload)),
                category="run",
                action="run",
            )

        def _post_run_async(self, path: str, payload: dict[str, object]) -> int:
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (
                    202,
                    {
                        "job_id": job_manager.submit(service.run, payload),
                        "status": "queued",
                    },
                ),
                category="run",
                action="run_async",
                entity_type="job",
                entity_id_key="job_id",
            )

        def _post_undo(self, path: str, payload: dict[str, object]) -> int:
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.undo(payload)),
                category="undo",
                action="undo",
                entity_type="action",
                entity_id_key="id",
            )

        def _post_check(self, payload: dict[str, object]) -> int:
            model_names = _parse_name_list(payload.get("models"))
            probe_prompt = str(payload.get("probe") or "Reply with: OK")
            out = service.check(
                config_path=_to_path(payload.get("config")),
                model_names=model_names or None,
                probe_prompt=probe_prompt,
            )
            self._send_json(200, out)
            return 200

        def _post_plugin_call(self, path: str, payload: dict[str, object]) -> int:
            plugin_name = path.removeprefix("/plugins/").removesuffix("/call").strip("/")
            if not plugin_name:
                self._send_json(404, {"error": "Not found"})
                return 404
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.plugin_call(plugin_name, payload)),
                category="plugins",
                action="call",
                entity_type="plugin",
                entity_id=plugin_name,
            )

        def _post_feedback(self, path: str, payload: dict[str, object]) -> int:
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (200, service.record_feedback(payload)),
                category="feedback",
                action="record",
                entity_type="feedback",
                entity_id_key="id",
            )

        def _respond_idempotent(
            self,
            *,
            path: str,
            payload: dict[str, object],
            operation,
            category: str,
            action: str,
            entity_type: str | None = None,
            entity_id: str | None = None,
            entity_id_key: str | None = None,
        ) -> int:
            status_code, response_payload, replayed = self._execute_idempotent(
                path,
                payload,
                operation,
            )
            resolved_entity_id = entity_id
            if resolved_entity_id is None and entity_id_key and isinstance(response_payload, dict):
                raw_entity = response_payload.get(entity_id_key)
                if raw_entity is not None:
                    resolved_entity_id = str(raw_entity)
            self._audit_event(
                category=category,
                action=action,
                status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
                entity_type=entity_type,
                entity_id=resolved_entity_id,
                payload=response_payload if isinstance(response_payload, dict) else None,
            )
            self._send_json(
                status_code,
                response_payload,
                replayed=replayed,
                idempotency_key=self._idempotency_key(),
            )
            return int(status_code)


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
            if path in {"/feedback"}:
                return True
            if path.startswith("/jobs/") and path.endswith("/cancel"):
                return True
            if path.startswith("/plugins/") and path.endswith("/call"):
                return True
            if path.startswith("/plans/") and (
                path.endswith("/approve")
                or path.endswith("/approve_async")
                or path.endswith("/retry_failed_async")
                or path.endswith("/retry_failed")
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
