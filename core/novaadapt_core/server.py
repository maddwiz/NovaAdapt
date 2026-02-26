from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections import deque
from http.server import ThreadingHTTPServer

from .audit_store import AuditStore
from .idempotency_store import IdempotencyStore
from .job_store import JobStore
from .jobs import JobManager
from .observability import configure_tracing
from .server_handler import _build_handler, _parse_trusted_proxy_cidrs
from .service import NovaAdaptService
from .terminal import TerminalSessionManager


DEFAULT_MAX_REQUEST_BODY_BYTES = 1 << 20  # 1 MiB


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
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_cls,
        service: NovaAdaptService,
        job_manager: JobManager,
        terminal_manager: TerminalSessionManager,
    ):
        super().__init__(server_address, handler_cls)
        self.service = service
        self.job_manager = job_manager
        self.terminal_manager = terminal_manager

    def server_close(self) -> None:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            manager.shutdown(wait=True)
        terminal_manager = getattr(self, "terminal_manager", None)
        if terminal_manager is not None:
            terminal_manager.close_all()
        service = getattr(self, "service", None)
        close_fn = getattr(service, "close", None)
        if callable(close_fn):
            close_fn()
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
    terminal_manager = TerminalSessionManager()
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
        terminal_manager=terminal_manager,
        metrics=metrics,
        max_request_body_bytes=max(1, int(max_request_body_bytes)),
    )
    return NovaAdaptHTTPServer((host, port), handler_cls, service, managed_jobs, terminal_manager)


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
