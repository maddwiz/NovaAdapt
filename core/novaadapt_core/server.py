from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .dashboard import render_dashboard_html
from .idempotency_store import IdempotencyStore
from .job_store import JobStore
from .jobs import JobManager
from .openapi import build_openapi_spec
from .service import NovaAdaptService


DEFAULT_MAX_REQUEST_BODY_BYTES = 1 << 20  # 1 MiB


class PayloadTooLargeError(ValueError):
    pass


class _SlidingWindowRateLimiter:
    """Simple thread-safe fixed-window limiter for API requests."""

    def __init__(self, burst: int, window_seconds: float = 1.0) -> None:
        self.burst = max(1, burst)
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.burst:
                return False
            self._timestamps.append(now)
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
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    jobs_db_path: str | None = None,
    idempotency_db_path: str | None = None,
) -> ThreadingHTTPServer:
    managed_jobs = job_manager or JobManager(store=JobStore(jobs_db_path) if jobs_db_path else None)
    idempotency_store = IdempotencyStore(idempotency_db_path) if idempotency_db_path else None
    metrics = _RequestMetrics()

    limiter = None
    if rate_limit_rps > 0:
        burst = rate_limit_burst if rate_limit_burst is not None else max(1, int(rate_limit_rps))
        limiter = _SlidingWindowRateLimiter(burst=burst, window_seconds=1.0)

    handler_cls = _build_handler(
        service=service,
        api_token=api_token,
        job_manager=managed_jobs,
        log_requests=log_requests,
        logger=logger or logging.getLogger("novaadapt.api"),
        limiter=limiter,
        idempotency_store=idempotency_store,
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
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    jobs_db_path: str | None = None,
    idempotency_db_path: str | None = None,
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
        max_request_body_bytes=max_request_body_bytes,
        jobs_db_path=jobs_db_path,
        idempotency_db_path=idempotency_db_path,
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
    limiter: _SlidingWindowRateLimiter | None,
    idempotency_store: IdempotencyStore | None,
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
                    status_code = 200
                    self._send_json(status_code, {"ok": True, "service": "novaadapt"})
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
                    config = _single(query, "config")
                    status_code = 200
                    self._send_json(
                        status_code,
                        {
                            "health": {"ok": True, "service": "novaadapt"},
                            "metrics": metrics.snapshot(),
                            "jobs": job_manager.list(limit=max(1, jobs_limit)),
                            "plans": service.list_plans(limit=max(1, plans_limit)),
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
            return not limiter.allow()

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
                if status in {"approved", "rejected", "executed"}:
                    self._write_sse_event(
                        "end",
                        {"id": plan_id, "status": status, "request_id": self._request_id},
                    )
                    return

                if time.monotonic() >= deadline:
                    self._write_sse_event("timeout", {"id": plan_id, "request_id": self._request_id})
                    return

                time.sleep(interval_seconds)

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
                self.path,
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
