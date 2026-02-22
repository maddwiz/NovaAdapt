from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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


class NovaAdaptHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls, job_manager: JobManager):
        super().__init__(server_address, handler_cls)
        self.job_manager = job_manager

    def server_close(self) -> None:
        self.job_manager.shutdown(wait=True)
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
) -> ThreadingHTTPServer:
    managed_jobs = job_manager or JobManager()
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

                if path == "/openapi.json":
                    status_code = 200
                    self._send_json(status_code, build_openapi_spec())
                    return

                if path == "/metrics":
                    if not self._check_auth(path):
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

                if not self._check_auth(path):
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
                    canceled = job_manager.cancel(job_id)
                    if canceled is None:
                        status_code = 404
                        self._send_json(status_code, {"error": "Job not found"})
                        return
                    status_code = 200
                    self._send_json(status_code, canceled)
                    return

                if path == "/run":
                    status_code = 200
                    self._send_json(status_code, service.run(payload))
                    return

                if path == "/run_async":
                    job_id = job_manager.submit(service.run, payload)
                    status_code = 202
                    self._send_json(status_code, {"job_id": job_id, "status": "queued"})
                    return

                if path == "/undo":
                    status_code = 200
                    self._send_json(status_code, service.undo(payload))
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

        def _check_auth(self, path: str) -> bool:
            if path == "/health" or not api_token:
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

        def _send_json(self, status_code: int, payload: object, unauthorized: bool = False) -> None:
            if isinstance(payload, dict):
                payload = dict(payload)
                payload.setdefault("request_id", self._request_id)
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", self._request_id)
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
